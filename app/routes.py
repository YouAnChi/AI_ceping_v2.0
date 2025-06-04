from flask import Blueprint, render_template, request, current_app, send_from_directory, url_for, jsonify, flash, redirect
from flask_login import login_required, current_user
from app.auth.routes import log_user_activity # 导入日志记录函数
from datetime import datetime
from ZhiBiao.achieve import extract_column_to_new_excel, process_and_evaluate_excel
import os
from werkzeug.utils import secure_filename
import uuid
import threading
from urllib.parse import urlparse, urlunparse # Added for URL parsing
import json # Added for json operations
from TQ.tools import extract_and_save_to_excel, extract_and_save_to_excel_folder, ai_prompt_query, load_prompts, analyze_excel
from app.models import UserActivityLog, User # Added for admin_user_activity
from app import db # Added for admin_user_activity

main_bp = Blueprint('main', __name__)

# A simple in-memory store for task statuses (NOT SUITABLE FOR PRODUCTION)
# Structure: tasks_status[task_id] = {'status': 'processing' | 'completed' | 'failed', 'progress': 0-100, 'message': '...', 'processed_filename': '...'}
tasks_status = {}

# Ensure PROCESSED_FILES_FOLDER is accessible for downloads
# It's usually configured in app.py, e.g., app.config['PROCESSED_FILES_FOLDER'] = 'processed_files'
# And UPLOADS_FOLDER for uploads, e.g., app.config['UPLOADS_FOLDER'] = 'uploads'

import requests # For making HTTP requests in test_connection

def process_task_background(app, task_id, processing_params):
    with app.app_context(): # Need app context for logging and config
        try:
            current_app.logger.info(f"Background processing started for task {task_id}")
            tasks_status[task_id]['status'] = 'processing'
            tasks_status[task_id]['progress'] = 60 # Simulate some progress

            final_excel_path = process_and_evaluate_excel(
                processing_params['questions_excel_path'],
                processing_params['output_dir'],
                processing_params['prompt'],
                processing_params['external_model_config'],
                processing_params['internal_model_config'],
                processing_params['selected_metrics'],
                processing_params.get('embedding_model_for_ass', 'BAAI/bge-small-zh-v1.5') # Pass to background task
            )
            
            if final_excel_path:
                processed_filename = os.path.basename(final_excel_path)
                tasks_status[task_id].update({
                    'status': 'completed', 
                    'progress': 100, 
                    'processed_filename': processed_filename
                })
                current_app.logger.info(f'Background processing complete for task {task_id}. Final file: {final_excel_path}')
            else:
                tasks_status[task_id].update({'status': 'failed', 'progress': 100, 'message': '处理和评估Excel失败'})
                current_app.logger.error(f'Background processing failed for task {task_id}: process_and_evaluate_excel returned None.')

        except Exception as e:
            current_app.logger.error(f'Exception during background processing for task {task_id}: {str(e)}')
            tasks_status[task_id].update({'status': 'failed', 'progress': 100, 'message': f'处理过程中发生内部错误: {str(e)}'})

@main_bp.route('/')
def index():
    log_message = f"Accessed index page at {datetime.now()} from {request.remote_addr}"
    current_app.logger.info(log_message)
    if current_user.is_authenticated:
        log_user_activity(current_user.id, 'view_index', f'User {current_user.username} accessed index page.')
    else:
        # 可以选择记录匿名用户的访问，或者不记录
        log_user_activity(None, 'view_index_anonymous', 'Anonymous user accessed index page.')
    return render_template('index.html')

@main_bp.route('/admin/user_activity')
@login_required # 暂时只要求登录，后续可以增加管理员权限检查
def admin_user_activity():
    # 检查是否是管理员，如果不是，则重定向或显示错误 (后续添加)
    # if not current_user.is_admin: # 假设 User 模型有 is_admin 属性
    #     flash('您没有权限访问此页面。', 'danger')
    #     return redirect(url_for('main.index'))

    page = request.args.get('page', 1, type=int)
    per_page = 20 # 每页显示的记录数
    activities_pagination = UserActivityLog.query.order_by(UserActivityLog.timestamp.desc()).paginate(page=page, per_page=per_page, error_out=False)
    activities = activities_pagination.items
    return render_template('admin/user_activity.html', title='用户活动日志', activities=activities, pagination=activities_pagination)

@main_bp.route('/subpage2')
def subpage2():
    log_message = f"Accessed subpage2 at {datetime.now()} from {request.remote_addr}"
    current_app.logger.info(log_message)
    return render_template('subpage2.html')

@main_bp.route('/function1', methods=['GET', 'POST'])
@login_required
def function1():
    log_message = f"Accessed function1 at {datetime.now()} from {request.remote_addr} with method {request.method} by user {current_user.username}"
    current_app.logger.info(log_message)
    log_user_activity(current_user.id, 'access_function1', f'Accessed function1. Method: {request.method}')

    embedding_models_list = []
    try:
        # Correct path to AI_test_utils/models from app/routes.py
        # current_app.root_path is /Users/lpd/Documents/project/ceping/AI_test_utils/app
        models_dir = os.path.join(current_app.root_path, '..', 'models')
        if os.path.exists(models_dir) and os.path.isdir(models_dir):
            # List subdirectories which are potential model names or organization folders
            current_app.logger.debug(f"Scanning models in {models_dir}. Initial items: {os.listdir(models_dir)}")
            for item_raw in os.listdir(models_dir):
                item = item_raw.strip()
                if not item or item.startswith('.'): # Skip hidden files/folders like ._____temp or .DS_Store
                    current_app.logger.debug(f"Skipping hidden/empty item: '{item_raw}'")
                    continue
                current_app.logger.debug(f"Processing item: '{item}'")
                item_path = os.path.join(models_dir, item)
                if os.path.isdir(item_path):
                    try:
                        # Check if item_path itself is a model directory (top-level model)
                        if any(f.lower().endswith(('.bin', '.safetensors', 'config.json')) for f in os.listdir(item_path)):
                            embedding_models_list.append(item)
                            current_app.logger.info(f"Found direct model: {item}")
                        else: # Check for org/model structure (e.g. BAAI/model_name)
                            current_app.logger.debug(f"Item '{item}' is an org folder. Checking sub-items...")
                            for sub_item_raw in os.listdir(item_path):
                                sub_item = sub_item_raw.strip()
                                if not sub_item or sub_item.startswith('.'): # Skip hidden files/folders in sub-directory
                                    current_app.logger.debug(f"Skipping hidden/empty sub_item: '{sub_item_raw}' in '{item}'")
                                    continue
                                current_app.logger.debug(f"Processing sub_item: '{sub_item}' in '{item}'")
                                sub_item_path = os.path.join(item_path, sub_item)
                                if os.path.isdir(sub_item_path):
                                    try:
                                        if any(f.lower().endswith(('.bin', '.safetensors', 'config.json')) for f in os.listdir(sub_item_path)):
                                            normalized_sub_item = sub_item.replace('___', '.')
                                            model_id = f"{item}/{normalized_sub_item}"
                                            embedding_models_list.append(model_id)
                                            current_app.logger.info(f"Found model: {model_id}")
                                        else:
                                            current_app.logger.debug(f"No model files found in sub_item_path: {sub_item_path}")
                                    except OSError as e_sub_list:
                                        current_app.logger.error(f"OSError listing sub_item_path {sub_item_path}: {e_sub_list}")
                                else:
                                    current_app.logger.debug(f"Sub_item '{sub_item_path}' is not a directory, skipping.")
                    except OSError as e_item_list:
                        current_app.logger.error(f"OSError listing item_path {item_path}: {e_item_list}")
                else:
                    current_app.logger.debug(f"Item '{item_path}' is not a directory, skipping.")
            embedding_models_list = sorted(list(set(embedding_models_list)))
        current_app.logger.info(f"Final embedding models found: {embedding_models_list}")
    except Exception as e:
        current_app.logger.error(f"Error scanning models directory: {e}")

    if request.method == 'POST':
        task_id = str(uuid.uuid4())
        tasks_status[task_id] = {'status': 'submitted', 'progress': 0, 'task_id': task_id}

        if 'excelFile' not in request.files:
            current_app.logger.error('No file part')
            tasks_status[task_id].update({'status': 'failed', 'message': '没有上传文件'})
            return jsonify(tasks_status[task_id]), 400
        
        file = request.files['excelFile']
        if file.filename == '':
            current_app.logger.error('No selected file')
            tasks_status[task_id].update({'status': 'failed', 'message': '没有选择文件'})
            return jsonify(tasks_status[task_id]), 400

        if file:
            try:
                filename = secure_filename(file.filename)
                # Ensure UPLOADS_FOLDER exists
                uploads_folder = current_app.config['UPLOADS_FOLDER']
                if not os.path.exists(uploads_folder):
                    os.makedirs(uploads_folder)
                uploaded_file_path = os.path.join(uploads_folder, f"{task_id}_{filename}")
                file.save(uploaded_file_path)
                current_app.logger.info(f'File {filename} uploaded to {uploaded_file_path} for task {task_id}')
                tasks_status[task_id]['progress'] = 10

                column_letter = request.form.get('questionColumn', 'A')
                current_app.logger.info(f'Selected column: {column_letter} for task {task_id}')
                
                # Ensure PROCESSED_FILES_FOLDER exists
                processed_files_folder = current_app.config['PROCESSED_FILES_FOLDER']
                if not os.path.exists(processed_files_folder):
                    os.makedirs(processed_files_folder)

                questions_excel_path = extract_column_to_new_excel(uploaded_file_path, column_letter, processed_files_folder)
                if not questions_excel_path:
                    current_app.logger.error(f'Failed to extract column from Excel for task {task_id}.')
                    tasks_status[task_id].update({'status': 'failed', 'message': '提取问题列失败'})
                    return jsonify(tasks_status[task_id]), 500
                current_app.logger.info(f'Questions extracted to {questions_excel_path} for task {task_id}')
                tasks_status[task_id]['progress'] = 30

                prompt = request.form.get('prompt', '')
                external_model_config = {
                    'key': request.form.get('external_model_key'),
                    'url': request.form.get('external_model_url'),
                    'name': request.form.get('external_model_name'),
                    'get_first_token': request.form.get('external_model_get_first_token') == 'true'
                }
                internal_model_config = {
                    'key': request.form.get('internal_model_key'),
                    'url': request.form.get('internal_model_url'),
                    'name': request.form.get('internal_model_name'),
                    'get_first_token': request.form.get('internal_model_get_first_token') == 'true'
                }
                selected_metrics = request.form.getlist('metrics')
                embedding_model_for_ass = request.form.get('embedding_model_for_ass', 'BAAI/bge-small-zh-v1.5') # Default if not provided
                current_app.logger.info(f'Selected embedding model for ASS: {embedding_model_for_ass}')
                tasks_status[task_id]['progress'] = 50

                processing_params = {
                    'questions_excel_path': questions_excel_path,
                    'output_dir': processed_files_folder,
                    'prompt': prompt,
                    'external_model_config': external_model_config,
                    'internal_model_config': internal_model_config,
                    'selected_metrics': selected_metrics,
                    'embedding_model_for_ass': embedding_model_for_ass
                }
                
                # Start background thread for processing
                thread = threading.Thread(target=process_task_background, args=(current_app._get_current_object(), task_id, processing_params))
                thread.daemon = True # Daemonize thread
                thread.start()

                tasks_status[task_id]['status'] = 'processing' # Update status to processing as thread starts
                current_app.logger.info(f'Task {task_id} submitted for background processing.')
                return jsonify(tasks_status[task_id])

            except Exception as e:
                current_app.logger.error(f'Error during initial processing for task {task_id}: {str(e)}')
                tasks_status[task_id].update({'status': 'failed', 'message': f'处理请求时发生内部错误: {str(e)}'})
                return jsonify(tasks_status[task_id]), 500

    # GET request handling (renders the initial page)
    return render_template('function1.html', embedding_models=embedding_models_list)



@main_bp.route('/function3', methods=['GET', 'POST'])
@login_required
def function3():
    log_message = f"Accessed function3 at {datetime.now()} from {request.remote_addr} with method {request.method} by user {current_user.username}"
    current_app.logger.info(log_message)
    log_user_activity(current_user.id, 'access_function3', f'Accessed function3. Method: {request.method}')
    
    if request.method == 'POST':
        try:
            files = request.files.getlist('fileUpload[]') # For multiple files / folder upload
            split_by = request.form.get('split_by', '\n')
            extraction_type = request.form.get('extraction_type', 'count')
            count = request.form.get('count', type=int)
            percentage = request.form.get('percentage', type=float)

            uploads_folder = current_app.config.get('UPLOADS_FOLDER', 'uploads')
            processed_folder = current_app.config.get('PROCESSED_FILES_FOLDER', 'processed_files')
            if not os.path.exists(uploads_folder):
                os.makedirs(uploads_folder)
            if not os.path.exists(processed_folder):
                os.makedirs(processed_folder)

            output_files = []

            if not files or all(f.filename == '' for f in files):
                return jsonify({'status': 'failed', 'message': '没有选择文件或文件夹'}), 400

            # Heuristic to check if it's a folder upload (multiple files with relative paths)
            # For a proper folder upload, client-side JS might package it, or server needs to handle path reconstruction.
            # The input `webkitdirectory` sends a list of files.
            # If only one file is selected, it's treated as a single file. If multiple, could be a folder's contents.

            # Simplified: if more than one file, assume it's contents of a directory to be processed individually
            # or if a single file, process that file.
            # A more robust solution for folder uploads would involve checking `file.content_type` or using a library.

            temp_upload_dir = os.path.join(uploads_folder, str(uuid.uuid4())) # Temporary directory for this request's uploads
            os.makedirs(temp_upload_dir, exist_ok=True)
            
            uploaded_file_paths = []
            is_folder_upload = len(files) > 1 # Simple heuristic

            for file in files:
                if file and file.filename:
                    filename = secure_filename(file.filename)
                    # If webkitdirectory is used, filenames might contain relative paths.
                    # We need to reconstruct the structure or treat them flatly.
                    # For simplicity, saving them flatly in temp_upload_dir.
                    file_path = os.path.join(temp_upload_dir, filename)
                    file.save(file_path)
                    uploaded_file_paths.append(file_path)
            
            if not uploaded_file_paths:
                 return jsonify({'status': 'failed', 'message': '未能成功保存任何上传的文件'}), 500

            if is_folder_upload or (len(uploaded_file_paths) == 1 and os.path.isdir(uploaded_file_paths[0])):
                # This part needs refinement. `extract_and_save_to_excel_folder` expects a folder path.
                # If files are uploaded flatly, we pass the temp_upload_dir.
                # tools.py saves output in the same folder as input by default, or CWD.
                # We want output in PROCESSED_FILES_FOLDER.
                # Modification: Pass output_dir to tq_tools functions.
                # For now, let's assume tq_tools.extract_and_save_to_excel_folder can take a list of files or a dir
                # and an output_dir parameter.
                # This part of tq_tools.py might need adjustment to accept an output_directory.
                # For now, we'll call it and expect it to save in processed_folder.
                # Let's assume the tool saves to its CWD or a fixed path, then we move it.
                
                # Let's assume extract_and_save_to_excel_folder works on temp_upload_dir
                # and we need to make its output go to processed_folder.
                # The tool currently returns full paths to generated excels.
                # We'll modify the tool to accept an output_dir or handle moving files.
                # For now, let's call it as is and see. It might save to CWD.
                # A better approach: modify tools.py to accept an output_dir.
                # For now, we'll call it and then try to provide download links assuming files are in processed_folder.

                # Simplified: Assume the tool saves to `processed_folder` if we could pass it.
                # Since we can't modify tools.py now, let's assume it saves to CWD or relative to script.
                # This will require manual moving of files or adjusting tools.py later.
                # For this step, we'll call the function and assume it returns paths we can serve.
                
                # Let's assume `extract_and_save_to_excel_folder` is adapted to take `output_base_dir`
                # and returns paths relative to that or absolute paths within it.
                # For now, this is a placeholder for the actual call.
                # result_paths = tq_tools.extract_and_save_to_excel_folder(temp_upload_dir, split_by, extraction_type, count, percentage, output_target_dir=processed_folder)
                # For now, let's just simulate a single file output for simplicity of frontend.
                # This part needs to be robustly implemented based on how tools.py works.
                
                # Let's process each file individually if it's a "folder" upload (multiple files)
                for single_file_path in uploaded_file_paths:
                    if single_file_path.lower().endswith('.txt'):
                        # The tool needs to be modified to accept an output directory.
                        # For now, assume it saves to processed_folder and returns the filename.
                        # This is a conceptual call, actual implementation depends on tools.py modification.
                        output_excel_path = extract_and_save_to_excel(
                            single_file_path, split_by, extraction_type, count, percentage,
                            output_dir=processed_folder # Assuming tools.py is modified for this
                        )
                        if output_excel_path:
                            output_files.append({
                                'name': os.path.basename(output_excel_path),
                                'url': url_for('main.download_file', filename=os.path.basename(output_excel_path))
                            })
            elif len(uploaded_file_paths) == 1:
                single_file_path = uploaded_file_paths[0]
                if single_file_path.lower().endswith('.txt'):
                    output_excel_path = extract_and_save_to_excel(
                        single_file_path, split_by, extraction_type, count, percentage,
                        output_dir=processed_folder # Assuming tools.py is modified for this
                    )
                    if output_excel_path:
                        output_files.append({
                            'name': os.path.basename(output_excel_path),
                            'url': url_for('main.download_file', filename=os.path.basename(output_excel_path))
                        })
                else:
                    return jsonify({'status': 'failed', 'message': '请上传.txt格式的文件'}), 400
            
            if not output_files:
                return jsonify({'status': 'failed', 'message': '未能处理文件或生成输出'}), 500

            return jsonify({'status': 'completed', 'files': output_files})

        except Exception as e:
            current_app.logger.error(f'Error in function3 POST: {str(e)}')
            return jsonify({'status': 'failed', 'message': f'处理请求时发生内部错误: {str(e)}'}), 500

    return render_template('function3.html')

# Background task for AI model evaluation (function4)
def process_evaluation_task_background(app, task_id, params):
    with app.app_context():
        try:
            current_app.logger.info(f"Background AI evaluation started for task {task_id}")
            tasks_status[task_id]['status'] = 'processing'
            tasks_status[task_id]['progress'] = 10

            # Load all available prompt templates
            all_prompts_data = []
            try:
                prompt_file_path_for_load = os.path.join(app.root_path, '..', 'TQ', 'PromptTemplate.json')
                all_prompts_data = load_prompts(prompt_file_path_for_load)
            except Exception as e:
                current_app.logger.error(f"Task {task_id}: Failed to load prompt templates: {e}")
                tasks_status[task_id].update({'status': 'failed', 'message': f'加载Prompt模板定义失败: {str(e)}'})
                return # Exit the background task

            current_excel_path = params['input_excel_path']
            final_modified_excel_path = None # Will store the path of the excel after all prompts are processed
            
            selected_prompt_names = params.get('selected_prompt_names', [])
            total_prompts_to_process = len(selected_prompt_names)
            prompts_processed_count = 0
            
            # Initial progress is 10, processing prompts will take from 10 up to 80 (70% of total progress range)

            for prompt_name_iter in selected_prompt_names:
                selected_prompt_object = next((p for p in all_prompts_data if p.get('name') == prompt_name_iter), None)
                
                if not selected_prompt_object or 'prompt' not in selected_prompt_object:
                    current_app.logger.warning(f"Task {task_id}: Prompt '{prompt_name_iter}' not found or has no content in PromptTemplate.json. Skipping.")
                    prompts_processed_count += 1
                    if total_prompts_to_process > 0:
                         current_progress_val = 10 + int((prompts_processed_count / total_prompts_to_process) * 70)
                         tasks_status[task_id]['progress'] = current_progress_val
                    if prompts_processed_count == total_prompts_to_process and final_modified_excel_path is None:
                        tasks_status[task_id].update({'status': 'failed', 'message': '所有选择的Prompt均无效或无法处理。'})
                    continue 

                prompt_content_iter = selected_prompt_object['prompt']
                output_column_name_iter = prompt_name_iter

                current_app.logger.info(f"Task {task_id}: Processing with prompt '{prompt_name_iter}'. Input: {current_excel_path}")
                
                modified_excel_path_for_this_prompt = ai_prompt_query(
                    current_excel_path, 
                    output_column_name_iter,
                    params['model_key'],
                    params['model_url'],
                    params['model_name'],
                    prompt_content_iter
                )

                if modified_excel_path_for_this_prompt and os.path.exists(modified_excel_path_for_this_prompt):
                    current_excel_path = modified_excel_path_for_this_prompt 
                    final_modified_excel_path = current_excel_path 
                    current_app.logger.info(f"Task {task_id}: Prompt '{prompt_name_iter}' processed. Output now at: {final_modified_excel_path}")
                else:
                    current_app.logger.error(f"Task {task_id}: Failed to process prompt '{prompt_name_iter}'. ai_prompt_query returned invalid path ('{modified_excel_path_for_this_prompt}') or file does not exist.")
                    tasks_status[task_id].update({
                        'status': 'failed', 
                        'message': f"处理Prompt '{prompt_name_iter}' 失败。",
                        'progress': tasks_status[task_id].get('progress', 10)
                    })
                    final_modified_excel_path = None 
                    break 

                prompts_processed_count += 1
                if total_prompts_to_process > 0:
                    current_progress_val = 10 + int((prompts_processed_count / total_prompts_to_process) * 70)
                    tasks_status[task_id]['progress'] = current_progress_val
            
            if final_modified_excel_path:
                 tasks_status[task_id]['progress'] = 80

            if final_modified_excel_path and os.path.exists(final_modified_excel_path):
                processed_filename = os.path.basename(final_modified_excel_path)
                # The function is already within 'with app.app_context():'.
                # Manually construct the relative URL to avoid issues with url_for in background threads without SERVER_NAME.
                analysis_results = None
                if final_modified_excel_path and os.path.exists(final_modified_excel_path):
                    try:
                        analysis_results = analyze_excel(final_modified_excel_path)
                        current_app.logger.info(f'Task {task_id}: Excel analysis complete for {final_modified_excel_path}. Results: {analysis_results}')
                    except Exception as ex_analyze:
                        current_app.logger.error(f'Task {task_id}: Error during Excel analysis for {final_modified_excel_path}: {str(ex_analyze)}')
                
                relative_download_url = f"/download_file/{processed_filename}"
                tasks_status[task_id].update({
                    'status': 'completed',
                    'progress': 100,
                    'message': 'AI模型评估处理成功完成。',
                    'processed_filename': processed_filename, # Keep for potential other uses
                    'download_url': relative_download_url, # Update to relative URL
                    'files': [{'name': processed_filename, 'url': relative_download_url}], # Add for consistency with function3
                    'analysis_results': analysis_results
                })
                current_app.logger.info(f'Background AI evaluation complete for task {task_id}. Output file: {final_modified_excel_path}')
            else:
                tasks_status[task_id].update({'status': 'failed', 'progress': 100, 'message': 'AI模型评估处理失败或未生成文件。'})
                current_app.logger.error(f'Background AI evaluation failed for task {task_id}: ai_prompt_query returned None or file does not exist.')

        except Exception as e:
            current_app.logger.error(f'Exception during background AI evaluation for task {task_id}: {str(e)}')
            tasks_status[task_id].update({'status': 'failed', 'progress': 100, 'message': f'处理过程中发生内部错误: {str(e)}'})

@main_bp.route('/function4', methods=['GET', 'POST'])
@login_required
def function4():
    log_message = f"Accessed function4 at {datetime.now()} from {request.remote_addr} with method {request.method} by user {current_user.username}"
    current_app.logger.info(log_message)
    log_user_activity(current_user.id, 'access_function4', f'Accessed function4. Method: {request.method}')

    if request.method == 'POST':
        task_id = str(uuid.uuid4())
        tasks_status[task_id] = {'status': 'submitted', 'progress': 0, 'task_id': task_id}

        try:
            if 'excelFile' not in request.files:
                tasks_status[task_id].update({'status': 'failed', 'message': '没有上传Excel文件'})
                return jsonify(tasks_status[task_id]), 400
            
            excel_file = request.files['excelFile']
            if excel_file.filename == '':
                tasks_status[task_id].update({'status': 'failed', 'message': '没有选择Excel文件'})
                return jsonify(tasks_status[task_id]), 400

            # Ensure PROCESSED_FILES_FOLDER exists (where input file will be saved and modified)
            processed_folder = current_app.config.get('PROCESSED_FILES_FOLDER', 'processed_files')
            if not os.path.exists(processed_folder):
                os.makedirs(processed_folder)

            filename = secure_filename(excel_file.filename)
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            # Save the uploaded file to be processed in place by ai_prompt_query
            input_excel_filename = f"{os.path.splitext(filename)[0]}_{timestamp}_{task_id}{os.path.splitext(filename)[1]}"
            input_excel_path = os.path.join(processed_folder, input_excel_filename)
            excel_file.save(input_excel_path)
            current_app.logger.info(f'File {filename} uploaded to {input_excel_path} for AI evaluation task {task_id}')
            tasks_status[task_id]['progress'] = 5

            model_key = request.form.get('model_key')
            model_url = request.form.get('model_url')
            model_name = request.form.get('model_name')
            selected_prompt_names = request.form.getlist('selected_prompts') # Get list of selected prompt names

            if not selected_prompt_names:
                tasks_status[task_id].update({'status': 'failed', 'message': '至少需要选择一个Prompt模板。'})
                current_app.logger.error(f'Task {task_id} failed: No prompt templates selected.')
                return jsonify(tasks_status[task_id]), 400
            
            current_app.logger.info(f'Task {task_id}: Selected prompts {selected_prompt_names}.')
            # Prompt content loading will now happen in the background task for each selected prompt.

            processing_params = {
                'input_excel_path': input_excel_path,
                'model_key': model_key,
                'model_url': model_url,
                'model_name': model_name,
                'selected_prompt_names': selected_prompt_names # Pass list of names
            }
            
            thread = threading.Thread(target=process_evaluation_task_background, args=(current_app._get_current_object(), task_id, processing_params))
            thread.daemon = True
            thread.start()

            tasks_status[task_id]['status'] = 'processing' # Update status as thread starts
            current_app.logger.info(f'AI evaluation task {task_id} submitted for background processing.')
            return jsonify(tasks_status[task_id])

        except Exception as e:
            current_app.logger.error(f'Error during initial processing for AI evaluation task {task_id}: {str(e)}')
            tasks_status[task_id].update({'status': 'failed', 'message': f'处理请求时发生内部错误: {str(e)}'})
            return jsonify(tasks_status[task_id]), 500

    # GET request: Render the page. Prompts and models will be fetched by JS.
    return render_template('function4.html')

@main_bp.route('/get_llm_models', methods=['GET'])
def get_llm_models():
    # In a real application, these would come from a config file, database, or API discovery
    # For now, hardcoding a list similar to function1.html's original dropdown
    # The frontend expects a list of objects like {id: 'model_id', name: 'Model Name'} or just a list of strings.
    # Let's provide a list of strings for simplicity, matching common model identifiers.
    models = [
        "deepseek-ai/DeepSeek-V2.5",
        "Qwen/Qwen3-30B-A3B",
        "THUDM/GLM-4-32B-0414",
        "internlm/internlm2_5-20b-chat"
        # Add more models as needed
        # "gpt-3.5-turbo", # Removed as per request
        # "gpt-4"          # Removed as per request
    ]
    # Convert to list of objects if frontend expects {id, name}
    # models_for_frontend = [{'id': m, 'name': m} for m in models]
    return jsonify(models) # Or jsonify(models_for_frontend)

@main_bp.route('/get_prompts', methods=['GET'])
def get_prompts():
    try:
        prompt_file_path = os.path.join(current_app.root_path, '..', 'TQ', 'PromptTemplate.json')
        prompts_data = load_prompts(prompt_file_path)
        if prompts_data is None: # load_prompts might return None on error
            prompts_data = []
        # Ensure it's a list of objects with 'name' and 'prompt' keys as expected by frontend
        # The current load_prompts seems to return this structure already.
        return jsonify(prompts_data)
    except Exception as e:
        current_app.logger.error(f"Error loading prompts for /get_prompts endpoint: {e}")
        return jsonify([]), 500 # Return empty list on error

@main_bp.route('/test_ai_model_connection', methods=['POST'])
def test_ai_model_connection(): # Renamed for clarity
    data = request.get_json()
    api_key = data.get('api_key')
    api_url = data.get('api_url')
    model_name = data.get('model_name')

    if not api_url or not model_name:
        return jsonify({'success': False, 'message': 'API URL 和模型名称不能为空'}), 400

    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'
    
    # Construct a minimal payload for testing. For many OpenAI-compatible APIs,
    # a simple chat completion request with max_tokens=1 is a good test.
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": "Say hi"}],
        "max_tokens": 1
    }
    # Construct the test request URL more robustly
    parsed_url = urlparse(api_url)
    
    if "chat/completions" in parsed_url.path:
        # Assume it's a full, correct URL if 'chat/completions' is in the path
        test_request_url = api_url
    elif parsed_url.query:
        # If there are query parameters and it's not a chat/completions path,
        # assume it's a custom URL that should be used as is (e.g., Azure).
        test_request_url = api_url
    else:
        # No 'chat/completions' in path, and no query parameters.
        # Assume it's a base URL. Append /v1 (if not already versioned) and /chat/completions.
        temp_path = parsed_url.path.strip('/') # Path part, e.g., "" or "custom_base" or "custom_base/v2"
        path_segments = [s for s in temp_path.split('/') if s]

        ends_with_version_segment = False
        if path_segments:
            last_segment = path_segments[-1]
            # Check for patterns like v1, v2, v1_beta (simplified check: starts with 'v' and has a digit after 'v')
            if last_segment.startswith('v') and len(last_segment) > 1 and any(char.isdigit() for char in last_segment[1:]):
                ends_with_version_segment = True
        
        if not ends_with_version_segment:
            if temp_path: # If there was an original path, append /v1 to it
                temp_path = temp_path.rstrip('/') + '/v1'
            else: # No original path (e.g. http://host.com), so path becomes v1
                temp_path = 'v1'
        
        # Now temp_path is like "custom_base/v1" or "v1" or "custom_base/v2"
        # Append /chat/completions
        final_path_str = temp_path.rstrip('/') + '/chat/completions'
        
        # Ensure final_path_str starts with a slash for urlunparse
        if not final_path_str.startswith('/'):
            final_path_str = '/' + final_path_str
            
        # Reconstruct the URL with the new path, keeping original scheme, netloc etc., and empty query for this branch
        test_request_url = urlunparse(parsed_url._replace(path=final_path_str, query=''))

    try:
        response = requests.post(test_request_url, headers=headers, json=payload, timeout=10)
        if response.status_code == 200:
            # Further check if response is valid JSON and indicates success
            try:
                response_data = response.json()
                # A successful response usually has 'choices' or similar field
                if response_data.get('choices') or response_data.get('id'): # Check for common success indicators
                    current_app.logger.info(f"AI Model Connection test to {api_url} (model: {model_name}) successful.")
                    return jsonify({'success': True, 'message': '连接成功，模型可用。'}), 200
                else:
                    current_app.logger.warning(f"AI Model Connection test to {api_url} (model: {model_name}) returned 200 but response format unexpected: {response.text[:200]}")
                    return jsonify({'success': False, 'message': f'连接成功但响应格式非预期。请确认模型名称和API端点。'}), 200 # Still 200 from server, but our check failed
            except ValueError: # JSONDecodeError inherits from ValueError
                current_app.logger.warning(f"AI Model Connection test to {api_url} (model: {model_name}) returned 200 but response is not valid JSON: {response.text[:200]}")
                return jsonify({'success': False, 'message': '连接成功但服务器响应不是有效的JSON。'}), 200
        else:
            error_message = f'连接失败 (状态码: {response.status_code}). '
            try:
                err_details = response.json().get('error', {}).get('message', response.text[:100])
                error_message += err_details
            except ValueError:
                error_message += response.text[:100]
            current_app.logger.warning(f"AI Model Connection test to {api_url} (model: {model_name}) failed. Status: {response.status_code}, Response: {response.text[:200]}")
            return jsonify({'success': False, 'message': error_message}), response.status_code

    except requests.exceptions.Timeout:
        current_app.logger.error(f"AI Model Connection test to {api_url} (model: {model_name}) timed out.")
        return jsonify({'success': False, 'message': '连接超时。请检查API URL和网络连接。'}), 408
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"AI Model Connection test to {api_url} (model: {model_name}) failed with exception: {str(e)}")
        return jsonify({'success': False, 'message': f'连接请求失败: {str(e)}'}), 500
    except Exception as e:
        current_app.logger.error(f"An unexpected error occurred during AI model connection test to {api_url} (model: {model_name}): {str(e)}")
        return jsonify({'success': False, 'message': f'发生意外错误: {str(e)}'}), 500

@main_bp.route('/get_evaluation_progress/<task_id>', methods=['GET'])
def get_evaluation_progress(task_id):
    log_message = f"Polling AI evaluation progress for task_id {task_id} at {datetime.now()} from {request.remote_addr}"
    # current_app.logger.info(log_message) # Can be too verbose, uncomment if needed for debugging

    task_info = tasks_status.get(task_id)
    if not task_info:
        return jsonify({'status': 'error', 'message': '无效的任务ID或任务已过期'}), 404
    
    # Actual progress is updated by the background thread.
    # No need to simulate progress here if the background thread is doing its job.
    return jsonify(task_info)


@main_bp.route('/get_progress/<task_id>', methods=['GET'])
def get_progress(task_id): # This is for function1, keep it separate
    log_message = f"Polling progress for task_id {task_id} at {datetime.now()} from {request.remote_addr}"
    current_app.logger.info(log_message)

    task_info = tasks_status.get(task_id)
    if not task_info:
        return jsonify({'status': 'error', 'message': '无效的任务ID'}), 404
    
    if task_info['status'] == 'processing' and task_info['progress'] < 90: 
        task_info['progress'] += 5 
        if task_info['progress'] > 90: task_info['progress'] = 90

    return jsonify(task_info)

@main_bp.route('/task_status/<task_id>') # Generic, might be fine or need specific versions
def task_status(task_id):
    status = tasks_status.get(task_id, {'status': 'not_found', 'message': '任务未找到或已过期'})
    return jsonify(status)

@main_bp.route('/download_file/<filename>')
def download_file(filename):
    log_message = f"Download request for {filename} at {datetime.now()} from {request.remote_addr}"
    current_app.logger.info(log_message)
    
    directory = current_app.config['PROCESSED_FILES_FOLDER']
    if not os.path.isabs(directory):
        directory = os.path.join(current_app.root_path, '..', directory)
        directory = os.path.normpath(directory)

    current_app.logger.info(f"Attempting to send file from directory: {directory}, filename: {filename}")
    
    safe_filename = secure_filename(filename)
    # It's important that the filename stored in tasks_status (and thus used in url_for) is already safe
    # or that this sanitization matches how it was stored/generated.
    # If task_id is part of filename, it should be safe.
    
    file_path = os.path.join(directory, safe_filename)
    if not os.path.exists(file_path):
        current_app.logger.error(f"File not found for download: {file_path}")
        return jsonify({'status': 'error', 'message': '文件未找到'}), 404

    return send_from_directory(directory, safe_filename, as_attachment=True)