import random
import pandas as pd
from datetime import datetime
from openai import OpenAI
import os,time,json,re

def extract_and_save_to_excel(file_path, split_by='\n', extraction_type='count', count=None, percentage=None, output_dir=None):
    """
    从文本文件中随机抽取内容并保存到带时间戳的 Excel 文件中。

    参数:
        file_path (str): 输入的文本文件路径。
        split_by (str): 按照什么进行分割，默认为换行符 '\n'。
        extraction_type (str): 指定抽取方式，'count' 表示指定条数抽取，'percentage' 表示按百分比抽取。
        count (int): 如果 extraction_type 为 'count'，指定抽取的条数。
        percentage (float): 如果 extraction_type 为 'percentage'，指定抽取的百分比（0 到 100）。
    """
    # 检查文件是否存在
    if not os.path.exists(file_path):
        print("文件不存在，请检查路径是否正确！")
        return

    # 检查抽取方式是否合法
    if extraction_type not in ['count', 'percentage']:
        print("抽取方式不正确，请选择 'count' 或 'percentage'！")
        return

    # 检查抽取参数是否合理
    if extraction_type == 'count' and (count is None or count <= 0):
        print("指定条数抽取时，count 参数必须为正整数！")
        return
    if extraction_type == 'percentage' and (percentage is None or percentage < 0 or percentage > 100):
        print("按百分比抽取时，percentage 参数必须在 0 到 100 之间！")
        return

    # 读取文件内容
    content = None
    try:
        with open(file_path, 'r', encoding='gbk') as file:
            content = file.read()
    except UnicodeDecodeError:
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
        except Exception as e:
            print(f"读取文件时出错（尝试了gbk和utf-8）：{e}")
            return
    except Exception as e:
        print(f"读取文件时出错：{e}")
        return

    if content is None:
        return

    # 验证分割符不能为空字符串
    if not split_by:
        split_by = '\n'  # 如果分割符为空，使用默认换行符
    
    # 按照指定分割符分割内容
    items = content.split(split_by)
    items = [item.strip() for item in items if item.strip()]  # 去除空白项

    # 根据抽取方式随机抽取内容
    if extraction_type == 'count':
        if count > len(items):
            print(f"指定条数 {count} 超过了总条数 {len(items)}，将抽取全部内容！")
            selected_items = items
        else:
            selected_items = random.sample(items, count)
    elif extraction_type == 'percentage':
        num_to_extract = int(len(items) * (percentage / 100))
        if num_to_extract == 0:
            num_to_extract += 1
        selected_items = random.sample(items, num_to_extract)

    # 创建带有时间戳的 Excel 文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"extracted_content_{os.path.splitext(os.path.basename(file_path))[0]}_{timestamp}.xlsx"
    if output_dir:
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        output_file = os.path.join(output_dir, output_filename)
    else:
        output_file = output_filename

    # 将抽取的内容保存到 Excel 文件中
    try:
        df = pd.DataFrame(selected_items, columns=['Extracted Content'])
        df.to_excel(output_file, index=False)
        print(f"抽取的内容已成功保存到 {output_file} 文件中！")
    except Exception as e:
        print(f"保存到 Excel 文件时出错：{e}")
        return None

    return output_file



def extract_and_save_to_excel_folder(folder_path, split_by='\n', extraction_type='count', count=None, percentage=None, output_dir=None):
    """
    从指定文件夹中的所有txt文件中随机抽取内容并保存到带时间戳的Excel文件中。

    参数:
        folder_path (str): 输入的文件夹路径。
        split_by (str): 按照什么进行分割，默认为换行符 '\n'。
        extraction_type (str): 指定抽取方式，'count' 表示指定条数抽取，'percentage' 表示按百分比抽取。
        count (int): 如果 extraction_type 为 'count'，指定抽取的条数。
        percentage (float): 如果 extraction_type 为 'percentage'，指定抽取的百分比（0 到 100）。
    返回:
        list: 包含所有生成的Excel文件路径的数组。
    """
    # 检查文件夹是否存在
    if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
        print("文件夹不存在，请检查路径是否正确！")
        return []

    # 检查抽取方式是否合法
    if extraction_type not in ['count', 'percentage']:
        print("抽取方式不正确，请选择 'count' 或 'percentage'！")
        return []

    # 检查抽取参数是否合理
    if extraction_type == 'count' and (count is None or count <= 0):
        print("指定条数抽取时，count 参数必须为正整数！")
        return []
    if extraction_type == 'percentage' and (percentage is None or percentage < 0 or percentage > 100):
        print("按百分比抽取时，percentage 参数必须在 0 到 100 之间！")
        return []

    excel_files = []

    # 遍历文件夹中的所有txt文件
    for filename in os.listdir(folder_path):
        if filename.endswith(".txt"):
            file_path = os.path.join(folder_path, filename)

            # 读取文件内容
            content = None
            try:
                with open(file_path, 'r', encoding='gbk') as file:
                    content = file.read()
            except UnicodeDecodeError:
                try:
                    with open(file_path, 'r', encoding='utf-8') as file:
                        content = file.read()
                except Exception as e:
                    print(f"读取文件 {filename} 时出错（尝试了gbk和utf-8）：{e}")
                    continue
            except Exception as e:
                print(f"读取文件 {filename} 时出错：{e}")
                continue

            if content is None:
                continue

            # 验证分割符不能为空字符串
            current_split_by = split_by
            if not current_split_by:
                current_split_by = '\n'  # 如果分割符为空，使用默认换行符
            
            # 按照指定分割符分割内容
            items = content.split(current_split_by)
            items = [item.strip() for item in items if item.strip()]  # 去除空白项

            # 根据抽取方式随机抽取内容
            if extraction_type == 'count':
                if count > len(items):
                    print(f"指定条数 {count} 超过了总条数 {len(items)}，将抽取全部内容！")
                    selected_items = items
                else:
                    selected_items = random.sample(items, count)
            elif extraction_type == 'percentage':
                num_to_extract = int(len(items) * (percentage / 100))
                if num_to_extract == 0:
                    num_to_extract += 1
                selected_items = random.sample(items, num_to_extract)

            # 创建带有时间戳的Excel文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_filename = os.path.splitext(filename)[0]
            output_filename = f"extracted_content_{base_filename}_output_{timestamp}.xlsx"
            if output_dir:
                if not os.path.exists(output_dir):
                    os.makedirs(output_dir)
                output_path = os.path.join(output_dir, output_filename)
            else:
                # Default to saving in the input folder_path if no output_dir is specified
                output_path = os.path.join(folder_path, output_filename)

            # 将抽取的内容保存到Excel文件中
            try:
                df = pd.DataFrame(selected_items, columns=['Extracted Content'])
                df.to_excel(output_path, index=False)
                print(f"文件 {filename} 的抽取内容已成功保存到 {output_path} 文件中！")
                excel_files.append(output_path)
            except Exception as e:
                print(f"保存文件 {filename} 到Excel文件时出错：{e}")

    return excel_files




def ai_prompt_query(file_path, output_response_column_name, key, url, model_name, prompt):
    """
    使用OpenAI模型处理提示词转换后的问题，并将结果添加到原来文件中。

    :param file_path: 文件路径
    :param output_response_column_name: 模型响应将写入的列名
    :param key: OpenAI API密钥
    :param url: OpenAI API URL
    :param model_name: 使用的OpenAI模型名称
    :param prompt: 提示词（可选）
    :return: 修改后的文件路径
    """

    # 读取 Excel 文件
    try:
        df = pd.read_excel(file_path)
        print("ai提示词处理模块启动，文件读取成功！")
    except Exception as e:
        print(f"ai提示词处理模块启动，读取 Excel 文件时出错：{e}")
        exit()

    # 获取第二列和第三列的内容（索引为 0 和 1）
    if len(df.columns) >= 2:  # 确保有足够的列
        column_bs = df.iloc[:, 0]  # 第一列
        column_cs = df.iloc[:, 1]  # 第二列
    else:
        print("Excel 文件中列数不足，请确保至少有三列。")
        return None
    
    try:
        client = OpenAI(api_key=key, base_url=url)
        responses_list = []

        for index, column_b in enumerate(column_bs):

            questions = prompt.replace("text1", str(column_b)).replace("text2", str(column_cs[index]))
            print(questions)
            start_time = time.time()

            messages = [{"role": "user", "content": str(questions)}]

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
                    full_response += content
                    full_response_reasoning += content
                    # print(content, end="", flush=True) # Optional: for live printing
                if reasoning_content:
                    # 模型生成的推理过程，后续添加到日志中。
                    full_response_reasoning += reasoning_content
                    # print(reasoning_content, end="", flush=True) # Optional: for live printing
            # print() # Optional: for live printing

            responses_list.append(full_response)
            print('-'*10)
        df[output_response_column_name] = pd.Series(responses_list, index=df.head(len(questions)).index)
        df.to_excel(file_path, index=False)

        print(f'总耗时：{time.time() - start_time}')
        
        return file_path
    except Exception as e:
        print(f"发生错误 (ai_prompt_query): {e}")
        return None
    
# 加载提示词
def load_prompts(file_path):
    # 读取 JSON 文件
    print("提示词加载模块启用！")
    # Construct absolute path to the prompts file relative to this script's directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    absolute_file_path = os.path.join(current_dir, file_path)
    try:
        with open(absolute_file_path, 'r', encoding='utf-8') as file:
            prompts = json.load(file)
        return prompts
    except FileNotFoundError:
        print(f"Error: Prompts file not found at {absolute_file_path}")
        return [] # Return empty list or raise error as appropriate
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {absolute_file_path}")
        return []



def extract_numbers(text):
    """从文本中提取所有数字（包括小数）"""
    numbers = re.findall(r'[-+]?\d*\.\d+|[-+]?\d+', text)
    return [float(num) for num in numbers]

def analyze_excel(file_path):
    """获取Excel中的分数并进行求值"""
    # 读取Excel文件
    df = pd.read_excel(file_path, engine='openpyxl')
    
    # 初始化结果字典
    results = {}
    
    # 遍历第三列及之后的列
    for column in df.columns[2:]:
        results[column] = {'count': 0, 'sum': 0, 'average': None, 'scores': []}
        numbers_list = []
        
        # 提取列中的数字
        for item in df[column]:
            # Ensure item is a string before trying to extract numbers
            str_item = str(item)
            # Skip processing if item is 'nan' or empty after stripping whitespace
            if str_item.lower() == 'nan' or not str_item.strip():
                continue
            numbers = extract_numbers(str_item)
            numbers_list.extend(numbers)
            for num in numbers:
                # Only include numbers in the calculation, assuming scores are typically positive
                # and within a certain range, e.g. 0-5 or 0-100. Adjust as needed.
                # For this example, let's assume scores are positive and we just sum them up.
                # The original code had `if num <= 5:`, which might be specific to a 5-point scale.
                # We will make it more general by just checking if it's a number.
                results[column]['count'] += 1
                results[column]['sum'] += num
                results[column]['scores'].append(num)
        
        # 计算平均值
        if results[column]['count'] > 0:
            results[column]['average'] = results[column]['sum'] / results[column]['count']
    
    return results

# 示例调用
# extract_and_save_to_excel('cilin.txt', split_by='\n', extraction_type='count', count=10)
# extract_and_save_to_excel('cilin.txt', split_by='\n', extraction_type='percentage', percentage=1)
# extraction_type count\percentage

# excel_files = extract_and_save_to_excel_folder(f'F:\PythonProject\AI_Project\AI_test_utils\\test', split_by='\n', extraction_type='count', percentage=10)
# excel_files = extract_and_save_to_excel_folder(f'F:\PythonProject\AI_Project\AI_test_utils\\test', split_by='\n', extraction_type='percentage', percentage=1)
# extraction_type count\percentage


prompts = load_prompts('PromptTemplate.json') # This call will now use the absolute path logic inside load_prompts
# for prompt in prompts:
#     print(f"功能名称: {prompt['name']}")
#     print(f"提示词内容: {prompt['prompt']}\n")


# key = 'sk-ptaneqxtvnazobcjgrnukaerzqmbjciacwbirtmekesqlrad'
# url = 'https://api.siliconflow.cn/v1/'
# model_name = 'deepseek-ai/DeepSeek-V2.5'
# 
# for prompt_item in prompts: # Renamed variable to avoid conflict
#     if prompt_item['name'] == '完整度': # Updated to a valid name from PromptTemplate.json
#         selected_prompt = prompt_item['prompt'] # Use a different variable for the selected prompt
#         break
# 
# ai_prompt_query('111.xlsx','完整度评估',key,url,model_name,selected_prompt) # Updated column name and prompt variable
