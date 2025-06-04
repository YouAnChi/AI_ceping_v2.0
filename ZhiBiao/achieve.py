import pandas as pd
import os, time, uuid
from datetime import datetime
from openai import OpenAI
from sentence_transformers import SentenceTransformer
import numpy as np
from rouge import Rouge
import jieba
from modelscope.hub.snapshot_download import snapshot_download
import shutil # Added for robustly moving files if necessary
from collections import defaultdict # Added for CILIN F1 calculation

def extract_column_to_new_excel(input_excel_path, column_letter, output_dir):
    """
    从指定的Excel文件中提取指定列的内容，并将其写入一个新的Excel文件中。
    新文件的名称是唯一的，并返回新文件的路径。

    :param input_excel_path: 输入的Excel文件路径
    :param column_letter: 需要提取的列的字母（如A、B、C等）
    :param output_dir: 提取后文件的保存目录
    :return: 新创建的Excel文件的路径
    """
    try:
        # 读取输入的Excel文件
        df = pd.read_excel(input_excel_path)

        # 将列字母转换为列索引（从0开始）
        column_index = ord(column_letter.upper()) - ord('A')

        # 检查列索引是否超出范围
        if column_index >= len(df.columns):
            raise ValueError(f"指定的列 '{column_letter}' 超出了Excel文件的列范围。")

        # 提取指定列的内容
        extracted_column = df.iloc[:, [column_index]]

        # 创建一个唯一的文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]  # 取UUID的前8位作为唯一标识
        output_file_name = f"extracted_{column_letter}_{timestamp}_{unique_id}.xlsx"
        # 文件存放路径
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        output_file_path = os.path.join(output_dir, output_file_name)

        # 将提取的列写入新的Excel文件
        extracted_column.to_excel(output_file_path, index=False)

        print(f"新文件已创建，路径为: {output_file_path}")
        return output_file_path

    except Exception as e:
        print(f"发生错误: {e}")
        return None



def query_ai_model_with_excel(df_input, question_column_name, output_response_column_name, output_first_token_column_name, key, url, model_name, get_first_token, prompt=None):
    """
    使用OpenAI模型处理DataFrame中的问题，并将结果添加到DataFrame中。

    :param df_input: 输入的DataFrame，包含问题列
    :param question_column_name: 问题列的名称
    :param output_response_column_name: 模型响应将写入的列名
    :param output_first_token_column_name: 首token时间将写入的列名
    :param key: OpenAI API密钥
    :param url: OpenAI API URL
    :param model_name: 使用的OpenAI模型名称
    :param get_first_token: 是否获取首token
    :param prompt: 提示词（可选）
    :return: 修改后的DataFrame副本，包含模型响应和首token时间
    """
    df_output = df_input.copy()
    try:
        client = OpenAI(api_key=key, base_url=url)
        questions = df_output[question_column_name].dropna().tolist()

        responses_list = []
        first_tokens_list = []

        for index, question_text in enumerate(questions):
            start_time = time.time()
            first_token_received = False
            first_token_time_val = None

            messages = [{"role": "user", "content": str(question_text)}]
            if prompt:
                messages.insert(0, {"role": "system", "content": prompt})

            response_stream = client.chat.completions.create(
                model=model_name,
                messages=messages,
                stream=True
            )

            full_response = ""
            full_response_reasoning = ""
            for chunk in response_stream:
                if not chunk.choices:
                    continue
                # 模型生成的直接文本回复
                content = chunk.choices[0].delta.content
                # 模型生成内容背后的推理过程
                reasoning_content = chunk.choices[0].delta.reasoning_content
                
                if content:
                    if not first_token_received:
                        first_token_time_val = time.time() - start_time
                        first_token_received = True
                    full_response += content
                    full_response_reasoning += content
                    # print(content, end="", flush=True) # Optional: for live printing
                if reasoning_content:
                    # 模型生成的推理过程，后续添加到日志中。
                    full_response_reasoning += reasoning_content
                    # print(reasoning_content, end="", flush=True) # Optional: for live printing
            # print() # Optional: for live printing

            responses_list.append(full_response)
            if get_first_token:
                first_tokens_list.append(first_token_time_val)
            else:
                first_tokens_list.append(None) # Keep lists aligned

        df_output[output_response_column_name] = pd.Series(responses_list, index=df_output.head(len(questions)).index)
        if get_first_token:
            df_output[output_first_token_column_name] = pd.Series(first_tokens_list, index=df_output.head(len(questions)).index)

        return df_output

    except Exception as e:
        print(f"发生错误 (query_ai_model_with_excel): {e}")
        # Return original dataframe with potentially empty new columns on error to avoid breaking flow
        if output_response_column_name not in df_output.columns:
             df_output[output_response_column_name] = None
        if get_first_token and output_first_token_column_name not in df_output.columns:
             df_output[output_first_token_column_name] = None
        return df_output



# --- Start of CILIN F1 Calculation Code ---
CILIN_DATA = None # 初始化 CILIN_DATA，存储 (word_to_direct_synonyms, word_to_codes, code_prefix_to_words)

def load_cilin(cilin_path):
    """
    加载哈工大词林文件。
    每行格式可能为 '编码 词1 词2 ...' 或 '编码=词1 词2 ...'。
    构建以下数据结构:
    1. word_to_direct_synonyms: 词 -> {同义词集合} (同一行内的词互为同义词)
    2. word_to_codes: 词 -> {词林编码集合} (一个词可能对应多个编码)
    3. code_prefix_to_words: 词林编码前缀 -> {词集合} (用于层次化扩展)
    """
    global CILIN_DATA
    if CILIN_DATA is not None:
        return CILIN_DATA

    word_to_direct_synonyms = defaultdict(set)
    word_to_codes = defaultdict(set)
    code_to_words_temp = defaultdict(set) # 临时存储完整编码到词的映射
    code_prefix_to_words = defaultdict(set)

    processed_lines = 0
    malformed_lines = 0 # 记录格式不正确的行数

    try:
        with open(cilin_path, 'r', encoding='utf-8') as f:
            for line_number, line_content in enumerate(f, 1):
                line_content = line_content.strip()
                if not line_content:
                    continue

                parts = line_content.split(None, 1) # 按第一个空格分割
                if len(parts) < 2:
                    parts = line_content.split('=', 1)
                    if len(parts) < 2:
                        malformed_lines += 1
                        # print(f"Skipping malformed line {line_number}: {line_content} (无法分割编码和词语)")
                        continue
                
                cilin_code_raw = parts[0]
                words_str = parts[1].strip()
                actual_code = ''.join(filter(str.isalnum, cilin_code_raw))

                if not actual_code:
                    malformed_lines +=1
                    # print(f"Skipping malformed line {line_number}: {line_content} (编码处理后为空)")
                    continue
                
                current_line_words = {word for word in words_str.split() if word}
                if not current_line_words:
                    malformed_lines += 1
                    # print(f"Skipping malformed line {line_number}: {line_content} (没有有效词语)")
                    continue
                
                processed_lines += 1
                for word in current_line_words:
                    word_to_direct_synonyms[word].update(current_line_words)
                    word_to_codes[word].add(actual_code)
                code_to_words_temp[actual_code].update(current_line_words)

        meaningful_prefix_lengths = [1, 2, 4, 5] # 大类(1), 中类(2), 小类(4), 词群(5)

        for code_val, words in code_to_words_temp.items(): # Renamed 'code' to 'code_val'
            for length in meaningful_prefix_lengths:
                if len(code_val) >= length:
                    prefix = code_val[:length]
                    code_prefix_to_words[prefix].update(words)
        
        CILIN_DATA = (word_to_direct_synonyms, word_to_codes, code_prefix_to_words)
        print(f"词林加载完毕。共处理 {processed_lines} 行有效词条。")
        if malformed_lines > 0:
            print(f"警告：跳过了 {malformed_lines} 行格式不正确的词条。请检查词林文件格式。")
        return CILIN_DATA
    except FileNotFoundError:
        print(f"错误：词林文件未找到于路径 {cilin_path}")
        CILIN_DATA = None 
        return None
    except Exception as e:
        print(f"加载词林时发生未知错误: {e}")
        CILIN_DATA = None
        return None

def calculate_f1_with_cilin(input_excel_path, cilin_path):
    """
    计算两段中文文本之间的F1值，使用jieba进行分词和词林扩展。

    :param input_excel_path: 输入的Excel文件路径
    :param cilin_path: 哈工大词林文件路径
    """
    df = pd.read_excel(input_excel_path)

    if len(df.columns) < 3:
        print("错误: Excel文件需要至少3列（问题，模型1响应，模型2响应）才能计算F1值。")
        if 'F1值_词林_层次化' not in df.columns:
            df['F1值_词林_层次化'] = "列数不足"
        else:
            # Ensure assignment is safe even for empty df
            if not df.empty:
                 df.loc[df.index, 'F1值_词林_层次化'] = "列数不足"
            else:
                 df['F1值_词林_层次化'] = pd.Series(["列数不足"] if not df.empty else [], dtype=object)
        df.to_excel(input_excel_path, index=False)
        return

    responses_col1_name = df.columns[1] 
    responses_col2_name = df.columns[2] 

    texts_one = df[responses_col1_name].astype(str).fillna('').tolist()
    texts_two = df[responses_col2_name].astype(str).fillna('').tolist()
    
    min_len = min(len(texts_one), len(texts_two))
    
    output_column_name = 'F1值_词林_层次化'
    if output_column_name not in df.columns:
        df[output_column_name] = pd.Series([None] * len(df), dtype=object)

    print('开始F1值_词林_层次化评估...')
    start_time = time.time()

    cilin_data_tuple = load_cilin(cilin_path)
    if cilin_data_tuple is None:
        print(f"词林数据加载失败 (路径: {cilin_path})。跳过F1值_词林_层次化评估。")
        df[output_column_name] = "词林加载失败"
        df.to_excel(input_excel_path, index=False)
        return
    word_to_direct_synonyms, word_to_codes, code_prefix_to_words = cilin_data_tuple

    f1_scores = []
    for index in range(len(df)):
        if index >= min_len: 
            f1_scores.append(0.0) 
            continue

        text1 = texts_one[index]
        text2 = texts_two[index]
        
        tokens1 = set(jieba.cut(text1)) 
        tokens2 = set(jieba.cut(text2)) 

        expanded_tokens1 = set()
        for token in tokens1:
            expanded_tokens1.add(token) 
            if token in word_to_direct_synonyms: 
                expanded_tokens1.update(word_to_direct_synonyms[token])
            if token in word_to_codes: 
                for code_item in word_to_codes[token]: 
                    prefixes_lengths = [1, 2, 4, 5] 
                    for length in prefixes_lengths:
                        if len(code_item) >= length:
                            prefix = code_item[:length]
                            if prefix in code_prefix_to_words:
                                expanded_tokens1.update(code_prefix_to_words[prefix])
        
        expanded_tokens2 = set()
        for token in tokens2:
            expanded_tokens2.add(token) 
            if token in word_to_direct_synonyms: 
                expanded_tokens2.update(word_to_direct_synonyms[token])
            if token in word_to_codes: 
                for code_item in word_to_codes[token]: 
                    prefixes_lengths = [1, 2, 4, 5]
                    for length in prefixes_lengths:
                        if len(code_item) >= length:
                            prefix = code_item[:length]
                            if prefix in code_prefix_to_words:
                                expanded_tokens2.update(code_prefix_to_words[prefix])

        intersection = expanded_tokens1.intersection(expanded_tokens2)
        
        precision = len(intersection) / len(expanded_tokens2) if expanded_tokens2 else 0.0
        recall = len(intersection) / len(expanded_tokens1) if expanded_tokens1 else 0.0

        if precision + recall == 0:
            f1 = 0.0
        else:
            f1 = 2 * (precision * recall) / (precision + recall)
        
        f1_scores.append(f1)
    
    # Ensure f1_scores has an entry for every row in df, padding with 0.0 if necessary
    if len(f1_scores) < len(df):
        f1_scores.extend([0.0] * (len(df) - len(f1_scores)))
    
    df[output_column_name] = pd.Series(f1_scores, index=df.index)

    elapsed_time = time.time() - start_time
    hours, minutes, seconds_val = convert_seconds(elapsed_time)
    print(f'F1值_词林_层次化计算完成，共耗时：{hours}小时{minutes}分钟{seconds_val}秒。处理了 {len(f1_scores)} 条记录。')

    df.to_excel(input_excel_path, index=False)
    print(f"F1值_词林_层次化结果已更新到文件: {input_excel_path}")

# --- End of CILIN F1 Calculation Code ---

def process_and_evaluate_excel(questions_excel_path, output_dir, prompt,
                               external_model_config, internal_model_config,
                               selected_metrics, embedding_model_for_ass='BAAI/bge-small-zh-v1.5'):
    """
    核心处理函数：读取问题Excel，调用内外两个模型，合并结果，执行评估，并保存最终Excel。

    :param questions_excel_path: 只包含一列问题的Excel文件路径
    :param output_dir: 最终Excel文件的保存目录
    :param prompt: 通用提示词 (或按需调整为模型特定提示词)
    :param external_model_config: 外部模型配置字典 {key, url, name, get_first_token}
    :param internal_model_config: 内部模型配置字典 {key, url, name, get_first_token}
    :param selected_metrics: 用户选择的评估指标列表 (e.g., ['ass', 'rouge1'])
    :return: 处理完成的Excel文件路径, 或 None 如果失败
    """
    try:
        df_questions = pd.read_excel(questions_excel_path)
        if df_questions.empty or len(df_questions.columns) == 0:
            raise ValueError("问题Excel文件为空或没有列。")
        
        question_column_actual_name = df_questions.columns[0]
        
        # 准备一个基础DataFrame用于收集结果
        df_result = pd.DataFrame()
        df_result['Questions'] = df_questions[question_column_actual_name].dropna()
        if df_result.empty:
            raise ValueError("提取问题后DataFrame为空。")

        # 1. 调用外部模型
        print("调用外部模型...")
        df_result_with_ext = query_ai_model_with_excel(
            df_result.copy(), # Pass a copy to avoid unintended modifications
            'Questions',
            'External_Model_Response',
            'External_Model_First_Token',
            external_model_config['key'],
            external_model_config['url'],
            external_model_config['name'],
            external_model_config['get_first_token'],
            prompt
        )
        df_result['External_Model_Response'] = df_result_with_ext.get('External_Model_Response')
        if external_model_config['get_first_token']:
            df_result['External_Model_First_Token'] = df_result_with_ext.get('External_Model_First_Token')

        # 2. 调用内部模型
        print("调用内部模型...")
        df_result_with_int = query_ai_model_with_excel(
            df_result.copy(), # Pass a copy with only questions for internal model
            'Questions',
            'Internal_Model_Response',
            'Internal_Model_First_Token',
            internal_model_config['key'],
            internal_model_config['url'],
            internal_model_config['name'],
            internal_model_config['get_first_token'],
            prompt
        )
        df_result['Internal_Model_Response'] = df_result_with_int.get('Internal_Model_Response')
        if internal_model_config['get_first_token']:
            df_result['Internal_Model_First_Token'] = df_result_with_int.get('Internal_Model_First_Token')

        # 确保评估函数所需的列顺序：Questions, External, Internal
        final_columns_order = ['Questions', 'External_Model_Response', 'Internal_Model_Response']
        if external_model_config['get_first_token'] and 'External_Model_First_Token' in df_result:
            final_columns_order.append('External_Model_First_Token')
        if internal_model_config['get_first_token'] and 'Internal_Model_First_Token' in df_result:
            final_columns_order.append('Internal_Model_First_Token')
        
        # Reorder df_result columns if necessary, handling missing columns gracefully
        current_cols = [col for col in final_columns_order if col in df_result.columns]
        df_result = df_result[current_cols]

        # 创建唯一文件名并保存包含模型响应的Excel
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        output_filename = f"eval_ready_{timestamp}_{unique_id}.xlsx"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        output_file_path = os.path.join(output_dir, output_filename)
        df_result.to_excel(output_file_path, index=False)
        print(f"模型响应已保存到: {output_file_path}")

        # 3. 执行评估指标计算
        if selected_metrics:
            print(f"开始评估指标计算: {selected_metrics}")
            if 'ass' in selected_metrics:
                print(f"计算ASS值 (使用嵌入模型: {embedding_model_for_ass})...")
                excel_ragas(output_file_path, embedding_model_identifier=embedding_model_for_ass) # Modifies file in place
            if 'rouge1' in selected_metrics:
                print("计算ROUGE-1...")
                excel_rouge(output_file_path, 'ROUGE-1') # Modifies file in place
            if 'rouge2' in selected_metrics:
                print("计算ROUGE-2...")
                excel_rouge(output_file_path, 'ROUGE-2') # Modifies file in place
            if 'rougel' in selected_metrics:
                print("计算ROUGE-L...")
                excel_rouge(output_file_path, 'ROUGE-L') # Modifies file in place
            if 'f1_chinese' in selected_metrics:
                print("计算F1值(中文分词)...")
                calculate_f1_chinese(output_file_path) # Modifies file in place
            if 'f1_cilin' in selected_metrics: # New metric for CILIN F1
                print("计算F1值(词林扩展)...")
                cilin_txt_path = f"/Users/lpd/Documents/project/ceping/AI_test_utils/ZhiBiao/cilin.txt"
                if os.path.exists(cilin_txt_path):
                    calculate_f1_with_cilin(output_file_path, cilin_txt_path) # Modifies file in place
                else:
                    print(f"错误：词林文件 {cilin_txt_path} 未找到。跳过F1值(词林扩展)计算。")
                    try:
                        temp_df = pd.read_excel(output_file_path)
                        output_col_name_cilin = 'F1值_词林_层次化'
                        if output_col_name_cilin not in temp_df.columns:
                            temp_df[output_col_name_cilin] = pd.Series([None] * len(temp_df), dtype=object)
                        # Ensure assignment is safe even for empty df
                        if not temp_df.empty:
                            temp_df.loc[temp_df.index, output_col_name_cilin] = "词林文件未找到"
                        else:
                            temp_df[output_col_name_cilin] = pd.Series(["词林文件未找到"] if not temp_df.empty else [], dtype=object)
                        temp_df.to_excel(output_file_path, index=False)
                    except Exception as e_excel:
                        print(f"写入词林未找到错误到Excel时出错: {e_excel}")
        
        print(f"所有处理和评估完成。最终文件: {output_file_path}")
        return output_file_path

    except Exception as e:
        print(f"处理Excel时发生严重错误 (process_and_evaluate_excel): {e}")
        import traceback
        traceback.print_exc()
        return None


def convert_seconds(seconds):
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = round(seconds % 60, 2)
    return hours, minutes, seconds

# Helper function to download/load model
def get_embedding_model(model_name_or_path='BAAI/bge-small-zh-v1.5', fallback_model='paraphrase-multilingual-MiniLM-L12-v2'):
    """
    Ensures the specified sentence embedding model is available, loading from a local path or downloading if necessary.
    Returns the SentenceTransformer model instance.
    Uses a fallback model if the primary model load/download fails.
    """
    project_root = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), '..'))
    model_base_dir = os.path.join(project_root, 'models')
    
    model_to_load = None

    # 1. Check if model_name_or_path is an absolute path to an existing directory
    if os.path.isabs(model_name_or_path) and os.path.isdir(model_name_or_path):
        print(f"检测到绝对路径模型: {model_name_or_path}")
        model_to_load = model_name_or_path
    else:
        # 2. Check if model_name_or_path is a relative path within model_base_dir
        potential_local_path = os.path.join(model_base_dir, model_name_or_path)
        if os.path.isdir(potential_local_path):
            print(f"检测到本地模型: {potential_local_path}")
            model_to_load = potential_local_path
        else:
            # 3. Assume it's a ModelScope ID to be downloaded.
            download_target_path = potential_local_path 
            print(f"模型 '{model_name_or_path}' 在本地路径 {download_target_path} 未找到或非目录，尝试从 ModelScope 下载...")
            try:
                if not os.path.exists(download_target_path) or not os.listdir(download_target_path):
                    print(f"开始下载 {model_name_or_path} 到 {model_base_dir} (目标子目录: {os.path.basename(download_target_path)})...")
                    # Ensure the parent directory of the download_target_path exists, 
                    # especially if model_name_or_path includes subdirectories like 'BAAI/bge-small-zh-v1.5'
                    os.makedirs(os.path.dirname(download_target_path), exist_ok=True)
                    
                    actual_downloaded_path = snapshot_download(model_name_or_path, cache_dir=model_base_dir)
                    print(f"模型 {model_name_or_path} 已下载到 {actual_downloaded_path}")
                    
                    if os.path.exists(download_target_path) and os.listdir(download_target_path):
                        model_to_load = download_target_path
                    elif os.path.exists(actual_downloaded_path) and os.listdir(actual_downloaded_path):
                         print(f"警告: 模型下载路径 {actual_downloaded_path} 与预期目标路径 {download_target_path} 不符，使用实际下载路径。")
                         model_to_load = actual_downloaded_path
                    else:
                        raise FileNotFoundError(f"模型下载后，路径 {download_target_path} (或 {actual_downloaded_path}) 仍然无效或为空。")
                else:
                    print(f"本地缓存模型 {download_target_path} 已存在。")
                    model_to_load = download_target_path
            except Exception as download_exc:
                print(f"从 ModelScope 下载或验证模型 {model_name_or_path} 失败: {download_exc}")
                model_to_load = None

    try:
        if model_to_load and os.path.isdir(model_to_load):
            print(f"加载 SentenceTransformer 模型: {model_to_load}")
            return SentenceTransformer(model_to_load)
        else:
            if model_to_load:
                 print(f"错误: 解析后的模型路径 '{model_to_load}' 不是一个有效的目录。")
            raise ValueError(f"无法确定或加载有效模型路径: '{model_name_or_path}'")

    except Exception as e:
        print(f"处理或加载模型 '{model_name_or_path}' (最终尝试路径: {model_to_load if model_to_load else 'N/A'}) 失败: {e}")
        print(f"尝试使用后备模型: {fallback_model}")
        try:
            return SentenceTransformer(fallback_model)
        except Exception as e_fallback:
            print(f"加载后备模型 {fallback_model} 也失败: {e_fallback}")
            raise  # Re-raise the exception if fallback also fails

def excel_ragas(input_excel_path, embedding_model_identifier='BAAI/bge-small-zh-v1.5'):
    """
    对excel中的B列与C列进行ASS值比较，生成比较值，并写入excel中。

    :param input_excel_path: 输入的Excel文件路径
    :param embedding_model_identifier: 用于ASS评估的嵌入模型的名称、ModelScope ID或本地路径
    """

    # 读取Excel文件
    df = pd.read_excel(input_excel_path)

    # 检查是否有足够的列
    if len(df.columns) < 2: # 需要至少两列用于比较 (e.g., External_Model_Response, Internal_Model_Response)
        raise ValueError("Excel文件中至少需要两列（例如，外部模型响应和内部模型响应）来进行比较。")

    # 获取第二列与第三列的内容作为问题
    # 这些索引现在应该对应于 'External_Model_Response' 和 'Internal_Model_Response'
    # 在 process_and_evaluate_excel 中，列的顺序是 Questions, External_Model_Response, Internal_Model_Response
    # 因此，我们比较 df.iloc[:, 1] 和 df.iloc[:, 2]
    questions_one = df.iloc[:, 1].dropna().tolist()
    questions_two = df.iloc[:, 2].dropna().tolist()

    if len(questions_one) != len(questions_two):
        print("警告: 用于ASS评估的两个答案列的长度不匹配。将按较短的列表长度进行处理。")
        min_len = min(len(questions_one), len(questions_two))
        questions_one = questions_one[:min_len]
        questions_two = questions_two[:min_len]

    # 准备结果列
    # 使用 embedding_model_identifier 来创建列名，以反映所使用的模型
    ass_column_name = f'ASS ({embedding_model_identifier})'
    if ass_column_name not in df.columns:
        df[ass_column_name] = pd.Series(dtype='float64') # Ensure float type for scores

    questions_len = len(questions_one)
    if questions_len == 0:
        print("没有可用于ASS评估的数据。")
        return
    
    # 批量数据进行ASS对比
    print(f'获取嵌入模型 ({embedding_model_identifier})...')
    try:
        model = get_embedding_model(embedding_model_identifier)
    except Exception as e:
        print(f"无法加载ASS评估所需的嵌入模型: {e}。ASS评估无法进行。")
        return

    start_time = time.time()
    ass_scores = []
    for index in range(questions_len):
        reference_answer = str(questions_one[index])
        generated_answer = str(questions_two[index])

        # 计算两个答案的嵌入向量
        embedding_1 = np.array(model.encode(reference_answer))
        embedding_2 = np.array(model.encode(generated_answer))

        print(f'进行ASS相似度计算，共{questions_len}条数据，计算第{index+1}条，请耐心等待。。。')

        # 计算余弦相似度
        norms_1 = np.linalg.norm(embedding_1, keepdims=True)
        norms_2 = np.linalg.norm(embedding_2, keepdims=True)
        
        if norms_1 == 0 or norms_2 == 0:
            similarity_score = 0.0 # Handle zero vectors
        else:
            embedding_1_normalized = embedding_1 / norms_1
            embedding_2_normalized = embedding_2 / norms_2
            similarity = embedding_1_normalized @ embedding_2_normalized.T
            similarity_score = similarity.item() # .flatten().tolist()[0] might fail if not scalar

        ass_scores.append(similarity_score)

    # 将完整响应写入DataFrame
    # Ensure the series is aligned with the original DataFrame's index for the relevant rows
    df.loc[df.iloc[:,1].dropna().index[:questions_len], ass_column_name] = ass_scores

    # 计算耗时
    end_time = time.time()
    elapsed_time = end_time - start_time
    hours, minutes, seconds = convert_seconds(elapsed_time)
    print(f'ASS相似度计算完成，共耗时：{hours}小时{minutes}分钟{seconds}秒')

    # 保存修改后的Excel文件
    df.to_excel(input_excel_path, index=False)

    print(f"ASS值已计算并保存到原文件: {input_excel_path}")

def excel_rouge(input_excel_path,rouge_index='ROUGE-1'):
    """
    rouge 库在处理中文文本时可能会有一些问题，因为它默认是为英文设计的。
    在 ROUGE 评估中，Precision（精确率）、Recall（召回率） 和 F1 Score（F1 分数） 是三个重要的指标，它们分别从不同的角度衡量生成文本与参考文本的相似度。
    Precision（精确率）：精确率反映了生成文本中有多大比例的内容是与参考文本匹配的。
    Recall（召回率）：召回率反映了参考文本中有多少内容被生成文本覆盖。
    F1 Score（F1 分数）：F1 分数是一个综合指标，平衡了精确率和召回率。它既考虑了生成文本的质量，也考虑了生成文本的完整性。

    :param input_excel_path: 输入的Excel文件路径
    :param rouge_index: 指标，可选项为ROUGE-1、ROUGE-2、ROUGE-L，默认为ROUGE-1
    """
    # 读取Excel文件
    df = pd.read_excel(input_excel_path)

    # 检查是否有足够的列
    if len(df.columns) < 2: # As per excel_ragas, expecting at least two columns for comparison
        raise ValueError("Excel文件中至少需要两列（例如，外部模型响应和内部模型响应）来进行ROUGE评估。")

    # 获取第二列与第三列的内容
    questions_one = df.iloc[:, 1].dropna().tolist()
    questions_two = df.iloc[:, 2].dropna().tolist()

    if len(questions_one) != len(questions_two):
        print("警告: 用于ROUGE评估的两个答案列的长度不匹配。将按较短的列表长度进行处理。")
        min_len = min(len(questions_one), len(questions_two))
        questions_one = questions_one[:min_len]
        questions_two = questions_two[:min_len]

    # 准备结果列
    if rouge_index not in df.columns:
        df[rouge_index] = pd.Series(dtype='float64')

    questions_len = len(questions_one)
    if questions_len == 0:
        print("没有可用于ROUGE评估的数据。")
        return

    # 初始化 ROUGE 计算器
    rouge = Rouge()
    print('加载ROUGE评估，请耐心等待。。。')

    start_time = time.time()
    rouge_scores = []
    for index in range(questions_len):
        reference_answer = str(questions_one[index])
        generated_answer = str(questions_two[index])

        print(f'进行ROUGE评估 ({rouge_index})，共{questions_len}条数据，计算第{index+1}条，请耐心等待。。。')

        # 处理空字符串的情况，rouge库可能无法处理
        if not reference_answer.strip() or not generated_answer.strip():
            print(f"警告: 第{index+1}条数据中存在空引用或生成答案，ROUGE得分将为0。")
            rouge_f1_score = 0.0
        else:
            try:
                scores = rouge.get_scores(generated_answer, reference_answer) # Note: order is hyp, ref
                if rouge_index == 'ROUGE-1':
                    rouge_f1_score = scores[0]['rouge-1']['f']
                elif rouge_index == 'ROUGE-2':
                    rouge_f1_score = scores[0]['rouge-2']['f']
                elif rouge_index == 'ROUGE-L':
                    rouge_f1_score = scores[0]['rouge-l']['f']
                else:
                    print(f"未知的ROUGE指标: {rouge_index}。将默认为0。")
                    rouge_f1_score = 0.0
            except Exception as e:
                print(f"计算第{index+1}条数据ROUGE得分时出错: {e}。得分为0。")
                rouge_f1_score = 0.0
        
        rouge_scores.append(rouge_f1_score)

    # 将完整响应写入DataFrame
    df.loc[df.iloc[:,1].dropna().index[:questions_len], rouge_index] = rouge_scores

    # 计算耗时
    end_time = time.time()
    elapsed_time = end_time - start_time
    hours, minutes, seconds_val = convert_seconds(elapsed_time)
    print(f'ROUGE ({rouge_index})评估完成，共耗时：{hours}小时{minutes}分钟{seconds_val}秒')

    # 保存修改后的Excel文件
    df.to_excel(input_excel_path, index=False)

    print(f"ROUGE ({rouge_index})值已计算并保存到原文件: {input_excel_path}")

def calculate_f1_chinese(input_excel_path):
    """
    计算两段中文文本之间的F1值，使用jieba进行分词。

    :param input_excel_path: 输入的Excel文件路径
    :param embedding_model_identifier: 用于ASS评估的嵌入模型的名称、ModelScope ID或本地路径
    """
    # 读取Excel文件
    df = pd.read_excel(input_excel_path)

    # 检查是否有足够的列
    if len(df.columns) < 2: # Expecting at least two columns for comparison
        raise ValueError("Excel文件中至少需要两列（例如，外部模型响应和内部模型响应）来进行F1值评估。")

    # 获取第二列与第三列的内容
    questions_one = df.iloc[:, 1].dropna().tolist()
    questions_two = df.iloc[:, 2].dropna().tolist()

    if len(questions_one) != len(questions_two):
        print("警告: 用于F1评估的两个答案列的长度不匹配。将按较短的列表长度进行处理。")
        min_len = min(len(questions_one), len(questions_two))
        questions_one = questions_one[:min_len]
        questions_two = questions_two[:min_len]

    # 准备结果列
    if 'F1值' not in df.columns:
        df['F1值'] = pd.Series(dtype='float64')

    questions_len = len(questions_one)
    if questions_len == 0:
        print("没有可用于F1评估的数据。")
        return

    print('加载F1值评估（中文分词），请耐心等待。。。')
    start_time = time.time()
    f1_scores = []

    for index in range(questions_len):
        reference_text = str(questions_one[index])
        generated_text = str(questions_two[index])

        print(f'进行F1值评估，共{questions_len}条数据，计算第{index+1}条，请耐心等待。。。')

        # 使用jieba进行分词
        try:
            # 添加默认词典，防止jieba未初始化
            jieba.initialize()
            reference_tokens = set(jieba.cut(reference_text))
            generated_tokens = set(jieba.cut(generated_text))
        except Exception as e:
            print(f"Jieba分词失败: {e}。请确保jieba已正确安装。")
            f1_scores.append(0.0)
            continue

        # 计算交集
        intersection = reference_tokens.intersection(generated_tokens)

        # 计算精确率和召回率
        precision = len(intersection) / len(generated_tokens) if len(generated_tokens) > 0 else 0
        recall = len(intersection) / len(reference_tokens) if len(reference_tokens) > 0 else 0

        # 计算F1值
        if precision + recall == 0:
            f1 = 0.0
        else:
            f1 = 2 * (precision * recall) / (precision + recall)
        
        f1_scores.append(f1)

    # 将完整响应写入DataFrame
    df.loc[df.iloc[:,1].dropna().index[:questions_len], 'F1值'] = f1_scores

    # 计算耗时
    end_time = time.time()
    elapsed_time = end_time - start_time
    hours, minutes, seconds_val = convert_seconds(elapsed_time)
    print(f'F1值（中文分词）评估完成，共耗时：{hours}小时{minutes}分钟{seconds_val}秒')

    # 保存修改后的Excel文件
    df.to_excel(input_excel_path, index=False)

    print(f"F1值已计算并保存到原文件: {input_excel_path}")

# The existing functions excel_ragas, excel_rouge, calculate_f1_chinese, convert_seconds
# and extract_column_to_new_excel remain largely unchanged below this point.
# Ensure they are compatible with the column structure (Questions, External, Internal)
# excel_ragas, excel_rouge, calculate_f1_chinese expect answers in df.iloc[:, 1] and df.iloc[:, 2]
# which corresponds to 'External_Model_Response' and 'Internal_Model_Response' in the saved df_result.

# Example usage (for testing, can be removed or commented out):
# if __name__ == '__main__':
#     # Create a dummy questions.xlsx for testing
#     dummy_questions_data = {'MyQuestions': ['Translate hello to Spanish', 'What is the capital of France?', 'Summarize this text: AI is cool.']}
#     dummy_df = pd.DataFrame(dummy_questions_data)
#     dummy_excel_path = 'dummy_questions.xlsx'
#     dummy_df.to_excel(dummy_excel_path, index=False)

#     test_output_dir = './test_output'
#     if not os.path.exists(test_output_dir):
#         os.makedirs(test_output_dir)

#     ext_config = {'key': 'YOUR_EXTERNAL_KEY', 'url': 'YOUR_EXTERNAL_URL', 'name': 'YOUR_EXTERNAL_MODEL', 'get_first_token': True}
#     int_config = {'key': 'YOUR_INTERNAL_KEY', 'url': 'YOUR_INTERNAL_URL', 'name': 'YOUR_INTERNAL_MODEL', 'get_first_token': True}
#     metrics = ['ass', 'rouge1'] #, 'f1_chinese']
#     prompt_text = "Please provide a concise answer."

#     # Test extract_column_to_new_excel
#     # Create a dummy multi-column excel for extract_column_to_new_excel test
#     dummy_multi_col_data = {'ColA': [1,2], 'ColB_Questions': ['Q1', 'Q2'], 'ColC': [3,4]}
#     dummy_multi_excel = 'dummy_multi.xlsx'
#     pd.DataFrame(dummy_multi_col_data).to_excel(dummy_multi_excel, index=False)
#     extracted_path = extract_column_to_new_excel(dummy_multi_excel, 'B', test_output_dir)
#     print(f"Extracted file for testing: {extracted_path}")

#     if extracted_path:
#         final_file = process_and_evaluate_excel(extracted_path, test_output_dir, prompt_text, ext_config, int_config, metrics)
#         if final_file:
#             print(f"Test completed. Final file: {final_file}")
#             # print(pd.read_excel(final_file))
#         else:
#             print("Test failed during process_and_evaluate_excel.")
#     else:
#         print("Test failed during extract_column_to_new_excel.")

#     # Cleanup dummy files
#     # if os.path.exists(dummy_excel_path): os.remove(dummy_excel_path)
#     # if os.path.exists(dummy_multi_excel): os.remove(dummy_multi_excel)
#     # if extracted_path and os.path.exists(extracted_path): os.remove(extracted_path)
#     # if final_file and os.path.exists(final_file): os.remove(final_file)


# calculate_f1_chinese('产品说明书1_AI生成的用例.xlsx')