# -*- coding: utf-8 -*-
"""
移动端授权管理系统 - Flask Web服务
适配iPhone Safari浏览器使用
"""

import os
import json
import time
import hashlib
import requests
import threading
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # 允许跨域请求

# 码云配置
GITEE_TOKEN = "ff0149c2c941b7bf43bca91e9fe6c8ec"
GITEE_REPO = "chav-pikey/license-serve"
GITEE_API_BASE = "https://gitee.com/api/v5"

class MobileAuthManager:
    """移动端授权管理器"""
    
    def __init__(self):
        self.api_base = GITEE_API_BASE
        self.processed_requests = set()
        self.load_processed_requests()
    
    def load_processed_requests(self):
        """从码云加载已处理的请求记录"""
        try:
            file_path = "processed_requests.json"
            url = f"{self.api_base}/repos/{GITEE_REPO}/contents/{file_path}"
            
            # 更激进的缓存破坏参数
            timestamp = int(time.time() * 1000)  # 毫秒级时间戳
            random_suffix = f"{timestamp % 10000}"  # 添加随机性
            
            params = {
                "access_token": GITEE_TOKEN,
                "_t": timestamp,
                "_r": random_suffix,
                "no_cache": "1"
            }
            
            # 更强的反缓存头
            headers = {
                'Cache-Control': 'no-cache, no-store, must-revalidate, max-age=0',
                'Pragma': 'no-cache',
                'Expires': '-1',
                'User-Agent': f'Mobile-Auth-Manager/1.0-{timestamp}',
                'If-None-Match': '*',  # 禁用ETag缓存
                'If-Modified-Since': 'Thu, 01 Jan 1970 00:00:00 GMT'  # 强制刷新
            }
            
            print(f"正在加载处理记录... 时间戳: {timestamp}")
            response = requests.get(url, params=params, headers=headers, timeout=15)
            
            if response.status_code == 200:
                file_info = response.json()
                
                # 检查返回的是文件还是文件夹
                if isinstance(file_info, dict) and 'content' in file_info:
                    # 正常文件
                    content = self._base64_decode(file_info['content'])
                    try:
                        processed_data = json.loads(content)
                        if isinstance(processed_data, list):
                            old_count = len(self.processed_requests) if hasattr(self, 'processed_requests') else 0
                            self.processed_requests = set(processed_data)
                            new_count = len(self.processed_requests)
                            print(f"处理记录更新: {old_count} -> {new_count} (时间戳: {timestamp})")
                            if old_count != new_count:
                                print(f"检测到新的处理记录变化!")
                            else:
                                print(f"处理记录无变化")
                        else:
                            print("处理记录格式错误，期望列表格式")
                            if not hasattr(self, 'processed_requests'):
                                self.processed_requests = set()
                    except json.JSONDecodeError as e:
                        print(f"处理记录JSON解析错误: {e}")
                        if not hasattr(self, 'processed_requests'):
                            self.processed_requests = set()
                elif isinstance(file_info, list):
                    # processed_requests.json 是个文件夹！这是问题所在
                    print(f"检测到 processed_requests.json 是文件夹而不是文件！")
                    print(f"文件夹内容: {[item.get('name', 'N/A') for item in file_info]}")
                    print(f"这解释了为什么需要重启服务器才能同步")
                    
                    # 初始化为空记录，因为无法从文件夹读取数据
                    if not hasattr(self, 'processed_requests'):
                        self.processed_requests = set()
                        
                    print(f"请手动删除Gitee仓库中的 processed_requests.json 文件夹")
                    print(f"系统将使用备用方案：不依赖处理记录文件")
                else:
                    print("处理记录文件内容格式错误")
                    if not hasattr(self, 'processed_requests'):
                        self.processed_requests = set()
            elif response.status_code == 404:
                print("处理记录文件不存在，使用空记录")
                if not hasattr(self, 'processed_requests'):
                    self.processed_requests = set()
            else:
                print(f"加载处理记录失败，状态码: {response.status_code}")
                if not hasattr(self, 'processed_requests'):
                    self.processed_requests = set()
                
        except requests.RequestException as e:
            print(f"网络请求失败，无法同步处理记录: {e}")
            if not hasattr(self, 'processed_requests'):
                self.processed_requests = set()
        except Exception as e:
            print(f"加载处理记录时出现异常: {e}")
            if not hasattr(self, 'processed_requests'):
                self.processed_requests = set()
    
    def get_pending_requests(self):
        """获取待处理的授权请求"""
        try:
            # 每次都重新加载已处理记录，确保与桌面版同步
            print(f"开始获取待处理请求...")
            self.load_processed_requests()
            
            url = f"{self.api_base}/repos/{GITEE_REPO}/contents/requests"
            
            # 更激进的缓存破坏
            timestamp = int(time.time() * 1000)  # 毫秒级时间戳
            random_id = f"{timestamp % 100000}"  # 5位随机数
            
            params = {
                "access_token": GITEE_TOKEN,
                "_t": timestamp,
                "_r": random_id,
                "no_cache": "1",
                "force_refresh": "1"
            }
            
            # 更强的反缓存头
            headers = {
                'Cache-Control': 'no-cache, no-store, must-revalidate, max-age=0, s-maxage=0, proxy-revalidate',
                'Pragma': 'no-cache',
                'Expires': '-1',
                'User-Agent': f'Mobile-Auth-Manager/1.0-{timestamp}',
                'If-None-Match': '*',
                'If-Modified-Since': 'Thu, 01 Jan 1970 00:00:00 GMT',
                'X-Requested-With': 'XMLHttpRequest'
            }
            
            print(f"请求文件夹列表... 时间戳: {timestamp}, 随机ID: {random_id}")
            response = requests.get(url, params=params, headers=headers, timeout=15)
            
            if response.status_code == 200:
                files = response.json()
                pending_requests = []
                
                print(f"从Gitee获取到 {len(files)} 个文件 (响应时间戳: {timestamp})")
                print(f"当前已处理记录数量: {len(self.processed_requests)}")
                if self.processed_requests:
                    print(f"已处理记录: {list(self.processed_requests)[:3]}..." if len(self.processed_requests) > 3 else f"已处理记录: {list(self.processed_requests)}")
                
                for file_info in files:
                    if file_info['name'].endswith('.json'):
                        file_path = file_info['path']
                        
                        # 直接检查文件内容状态，不依赖处理记录文件
                        print(f"检查文件: {file_info['name']}")
                        file_content = self._get_file_content(file_info['download_url'])
                        if file_content:
                            try:
                                request_data = json.loads(file_content)
                                current_status = request_data.get('status', 'unknown')
                                machine_code = request_data.get('machine_code', 'unknown')
                                
                                print(f"文件状态: {machine_code} -> {current_status}")
                                
                                # 只显示状态为pending的请求
                                if current_status == 'pending':
                                    # 检查请求时间，只处理24小时内的请求
                                    request_time_str = request_data.get('request_time', '')
                                    try:
                                        request_time = datetime.strptime(request_time_str, '%Y-%m-%d %H:%M:%S')
                                        time_diff = (datetime.now() - request_time).total_seconds()
                                        if 0 <= time_diff <= 86400:  # 24小时内
                                            request_data['file_path'] = file_path
                                            pending_requests.append(request_data)
                                            print(f"确认pending请求: {machine_code} - {request_time_str}")
                                        else:
                                            print(f"请求过旧: {machine_code} - {request_time_str} (距现在 {int(time_diff/3600)} 小时)")
                                    except Exception as e:
                                        print(f"时间解析失败: {e}")
                                        # 时间解析失败但状态为pending，仍然显示
                                        request_data['file_path'] = file_path
                                        pending_requests.append(request_data)
                                        print(f"时间解析失败但显示pending请求: {machine_code}")
                                else:
                                    print(f"跳过非pending请求: {machine_code} (状态: {current_status})")
                            except json.JSONDecodeError as e:
                                print(f"解析请求文件失败: {file_info['name']} - {e}")
                                continue
                        else:
                            print(f"无法获取文件内容: {file_info['name']}")
                
                # 按时间排序，最新的在前面
                pending_requests.sort(key=lambda x: x.get('request_time', ''), reverse=True)
                print(f"最终找到 {len(pending_requests)} 个有效的pending请求")
                return pending_requests
            else:
                print(f"获取requests文件夹失败，状态码: {response.status_code}")
                return []
                
        except Exception as e:
            print(f"获取请求失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def approve_request(self, machine_code, expire_hours=720):  # 默认30天
        """批准授权请求"""
        try:
            # 生成授权码
            expire_datetime = datetime.now() + timedelta(hours=expire_hours)
            license_code = self._generate_license_code(machine_code, expire_datetime)
            
            if license_code:
                # 创建响应数据
                response_data = {
                    "status": "approved",
                    "license_code": license_code,
                    "expire_datetime": expire_datetime.isoformat(),
                    "approve_time": datetime.now().isoformat(),
                    "machine_code": machine_code,
                    "approver": "MobileAuthTool"
                }
                
                # 上传响应到码云
                success, message = self._upload_response(machine_code, response_data)
                
                if success:
                    # 同时更新原始请求文件的状态为approved
                    success2 = self._update_request_status(machine_code, "approved")
                    if success2:
                        print(f"请求文件状态已更新为approved")
                    else:
                        print(f"请求文件状态更新失败，但响应已上传")
                    
                    # 标记为已处理（保留现有逻辑）
                    file_path = f"requests/{machine_code}.json"
                    self._mark_as_processed(file_path)
                    return True, f"授权成功，到期时间: {expire_datetime.strftime('%Y-%m-%d %H:%M:%S')}"
                else:
                    return False, f"上传响应失败: {message}"
            else:
                return False, "生成授权码失败"
                
        except Exception as e:
            return False, f"批准授权失败: {str(e)}"
    
    def reject_request(self, machine_code, reason="授权请求被拒绝"):
        """拒绝授权请求"""
        try:
            # 创建拒绝响应
            response_data = {
                "status": "rejected",
                "message": reason,
                "reject_time": datetime.now().isoformat(),
                "machine_code": machine_code,
                "rejector": "MobileAuthTool"
            }
            
            # 上传响应到码云
            success, message = self._upload_response(machine_code, response_data)
            
            if success:
                # 同时更新原始请求文件的状态为rejected
                success2 = self._update_request_status(machine_code, "rejected")
                if success2:
                    print(f"请求文件状态已更新为rejected")
                else:
                    print(f"请求文件状态更新失败，但响应已上传")
                
                # 标记为已处理（保留现有逻辑）
                file_path = f"requests/{machine_code}.json"
                self._mark_as_processed(file_path)
                return True, "已拒绝授权请求"
            else:
                return False, f"上传响应失败: {message}"
                
        except Exception as e:
            return False, f"拒绝授权失败: {str(e)}"
    
    def _generate_license_code(self, machine_code, expire_datetime):
        """生成授权码"""
        try:
            # 机器码验证部分
            machine_part = hashlib.sha256(f"MACHINE_{machine_code}_SALT".encode()).hexdigest()[:8].upper()
            
            # 日期时间部分
            date_part = expire_datetime.strftime('%Y%m%d')
            time_part = expire_datetime.strftime('%H%M%S')
            
            # 校验和
            data = f"{machine_code}_{expire_datetime.strftime('%Y%m%d%H%M%S')}_CHECKSUM"
            checksum = hashlib.md5(data.encode()).hexdigest()[:4].upper()
            
            # 组合授权码
            license_code = f"{machine_part}-{date_part}-{time_part}-{checksum}"
            return license_code.upper()
        except:
            return None
    
    def _upload_response(self, machine_code, response_data):
        """上传响应到码云"""
        try:
            file_path = f"responses/{machine_code}.json"
            content = json.dumps(response_data, ensure_ascii=False, indent=2)
            
            url = f"{self.api_base}/repos/{GITEE_REPO}/contents/{file_path}"
            data = {
                "access_token": GITEE_TOKEN,
                "content": self._base64_encode(content),
                "message": f"移动端授权响应: {machine_code}",
                "branch": "master"
            }
            
            response = requests.post(url, json=data, timeout=15)
            
            if response.status_code == 201:
                return True, "响应上传成功"
            else:
                # 可能文件已存在，尝试更新
                return self._update_response_file(file_path, content, machine_code)
        except Exception as e:
            return False, f"上传失败: {str(e)}"
    
    def _update_response_file(self, file_path, content, machine_code):
        """更新已存在的响应文件"""
        try:
            url = f"{self.api_base}/repos/{GITEE_REPO}/contents/{file_path}"
            params = {"access_token": GITEE_TOKEN}
            
            response = requests.get(url, params=params, timeout=15)
            if response.status_code == 200:
                file_info = response.json()
                if isinstance(file_info, dict) and 'sha' in file_info:
                    sha = file_info['sha']
                    data = {
                        "access_token": GITEE_TOKEN,
                        "content": self._base64_encode(content),
                        "message": f"更新移动端授权响应: {machine_code}",
                        "sha": sha,
                        "branch": "master"
                    }
                    
                    update_response = requests.put(url, json=data, timeout=15)
                    if update_response.status_code == 200:
                        return True, "响应更新成功"
            
            return False, "更新响应失败"
        except Exception as e:
            return False, f"更新失败: {str(e)}"
    
    def _mark_as_processed(self, file_path):
        """标记请求为已处理"""
        try:
            print(f"正在标记为已处理: {file_path}")
            self.processed_requests.add(file_path)
            
            # 立即保存到码云，确保同步
            processed_list = list(self.processed_requests)
            content = json.dumps(processed_list, ensure_ascii=False, indent=2)
            
            record_file_path = "processed_requests.json"
            url = f"{self.api_base}/repos/{GITEE_REPO}/contents/{record_file_path}"
            
            # 添加缓存破坏
            timestamp = int(time.time() * 1000)
            params = {
                "access_token": GITEE_TOKEN,
                "_t": timestamp,
                "no_cache": "1"
            }
            
            headers = {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '-1',
                'User-Agent': f'Mobile-Auth-Manager/1.0-{timestamp}'
            }
            
            print(f"检查处理记录文件是否存在...")
            response = requests.get(url, params=params, headers=headers, timeout=10)
            
            if response.status_code == 200:
                # 文件存在，更新
                print(f"更新现有处理记录文件...")
                file_info = response.json()
                if isinstance(file_info, dict) and 'sha' in file_info:
                    sha = file_info['sha']
                    data = {
                        "access_token": GITEE_TOKEN,
                        "content": self._base64_encode(content),
                        "message": f"移动端更新处理记录: {file_path} [{timestamp}]",
                        "sha": sha,
                        "branch": "master"
                    }
                    update_result = requests.put(url, json=data, timeout=15)
                    if update_result.status_code == 200:
                        print(f"处理记录更新成功!")
                    else:
                        print(f"处理记录更新失败: {update_result.status_code}")
            else:
                # 文件不存在，创建
                print(f"创建新的处理记录文件...")
                data = {
                    "access_token": GITEE_TOKEN,
                    "content": self._base64_encode(content),
                    "message": f"移动端创建处理记录: {file_path} [{timestamp}]",
                    "branch": "master"
                }
                create_result = requests.post(url, json=data, timeout=15)
                if create_result.status_code == 201:
                    print(f"处理记录创建成功!")
                else:
                    print(f"处理记录创建失败: {create_result.status_code}")
            
            print(f"当前已处理记录数量: {len(self.processed_requests)}")
            
        except Exception as e:
            print(f"标记处理失败: {e}")
    
    def _get_file_content(self, download_url):
        """获取文件内容，添加缓存破坏参数"""
        try:
            # 更激进的缓存破坏
            import urllib.parse
            parsed = urllib.parse.urlparse(download_url)
            
            # 毫秒级时间戳 + 随机数
            timestamp = int(time.time() * 1000)
            random_suffix = f"{timestamp % 999999}"
            
            # 多重缓存破坏参数
            cache_params = [
                f"_t={timestamp}",
                f"_r={random_suffix}", 
                f"no_cache=1",
                f"force_refresh=1",
                f"v={timestamp}"
            ]
            
            cache_buster = "&".join(cache_params)
            if parsed.query:
                new_query = f"{parsed.query}&{cache_buster}"
            else:
                new_query = cache_buster
                
            new_url = urllib.parse.urlunparse((
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                new_query,
                parsed.fragment
            ))
            
            # 最强的反缓存头部
            headers = {
                'Cache-Control': 'no-cache, no-store, must-revalidate, max-age=0, s-maxage=0, proxy-revalidate',
                'Pragma': 'no-cache',
                'Expires': '-1',
                'User-Agent': f'Mobile-Auth-Manager/1.0-{timestamp}',
                'If-None-Match': '*',
                'If-Modified-Since': 'Thu, 01 Jan 1970 00:00:00 GMT',
                'X-Requested-With': 'XMLHttpRequest',
                'Connection': 'close'  # 强制关闭连接
            }
            
            print(f"获取文件内容... URL长度: {len(new_url)}, 时间戳: {timestamp}")
            response = requests.get(new_url, headers=headers, timeout=15)
            if response.status_code == 200:
                content = response.text
                print(f"文件内容获取成功，长度: {len(content)} 字符")
                return content
            else:
                print(f"获取文件内容失败，状态码: {response.status_code}")
                return None
        except Exception as e:
            print(f"获取文件内容异常: {e}")
            return None
    
    def _update_request_status(self, machine_code, new_status):
        """更新请求文件的状态"""
        try:
            print(f"正在更新请求文件状态: {machine_code} -> {new_status}")
            
            request_file_path = f"requests/{machine_code}.json"
            url = f"{self.api_base}/repos/{GITEE_REPO}/contents/{request_file_path}"
            
            # 获取原始请求文件内容
            timestamp = int(time.time() * 1000)
            params = {
                "access_token": GITEE_TOKEN,
                "_t": timestamp,
                "no_cache": "1"
            }
            
            headers = {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '-1'
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            
            if response.status_code == 200:
                file_info = response.json()
                if isinstance(file_info, dict) and 'content' in file_info:
                    # 解码原始内容
                    original_content = self._base64_decode(file_info['content'])
                    request_data = json.loads(original_content)
                    
                    # 更新状态
                    request_data['status'] = new_status
                    request_data['status_update_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    
                    # 重新编码内容
                    updated_content = json.dumps(request_data, ensure_ascii=False, indent=2)
                    
                    # 更新文件
                    sha = file_info['sha']
                    update_data = {
                        "access_token": GITEE_TOKEN,
                        "content": self._base64_encode(updated_content),
                        "message": f"移动端更新请求状态: {machine_code} -> {new_status} [{timestamp}]",
                        "sha": sha,
                        "branch": "master"
                    }
                    
                    update_response = requests.put(url, json=update_data, timeout=15)
                    if update_response.status_code == 200:
                        print(f"请求文件状态更新成功: {machine_code} -> {new_status}")
                        return True
                    else:
                        print(f"请求文件状态更新失败: {update_response.status_code}")
                        return False
                else:
                    print(f"请求文件格式错误: {machine_code}")
                    return False
            else:
                print(f"获取请求文件失败: {machine_code}, 状态码: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"更新请求文件状态失败: {e}")
            return False
    
    def _base64_encode(self, text):
        """Base64编码"""
        import base64
        return base64.b64encode(text.encode('utf-8')).decode('utf-8')
    
    def _base64_decode(self, encoded_content):
        """解码码云返回的文件内容"""
        import base64
        try:
            content_str = str(encoded_content).replace('\n', '').replace(' ', '')
            decoded_bytes = base64.b64decode(content_str)
            return decoded_bytes.decode('utf-8')
        except Exception as e:
            raise Exception(f"Base64解码失败: {str(e)}")

# 全局授权管理器实例
auth_manager = MobileAuthManager()

# 路由定义
@app.route('/')
def index():
    """主页面"""
    return render_template('mobile_auth.html')

@app.route('/api/requests')
def api_get_requests():
    """API: 获取待处理请求"""
    try:
        requests_list = auth_manager.get_pending_requests()
        return jsonify({"success": True, "data": requests_list})
    except Exception as e:
        error_msg = f"获取请求列表失败: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": error_msg})

@app.route('/api/sync', methods=['POST'])
def api_force_sync():
    """API: 强制同步处理记录"""
    try:
        print("收到强制同步请求")
        auth_manager.load_processed_requests()
        requests_list = auth_manager.get_pending_requests()
        print(f"同步完成，当前待处理请求: {len(requests_list)}个")
        return jsonify({
            "success": True, 
            "message": "同步成功",
            "data": requests_list,
            "processed_count": len(auth_manager.processed_requests)
        })
    except Exception as e:
        error_msg = f"强制同步失败: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": error_msg})

@app.route('/api/approve', methods=['POST'])
def api_approve():
    """API: 批准授权"""
    try:
        # 获取请求数据
        if not request.is_json:
            return jsonify({"success": False, "error": "请求格式错误，需要JSON数据"}), 400
        
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "请求数据为空"}), 400
        
        machine_code = data.get('machine_code')
        expire_hours = data.get('expire_hours', 720)  # 默认30天
        
        if not machine_code:
            return jsonify({"success": False, "error": "机器码不能为空"}), 400
        
        # 验证参数
        try:
            expire_hours = int(expire_hours)
            if expire_hours <= 0:
                return jsonify({"success": False, "error": "授权期限必须大于0"}), 400
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "授权期限格式错误"}), 400
        
        print(f"收到批准请求: 机器码={machine_code}, 期限={expire_hours}小时")
        
        # 执行批准操作
        success, message = auth_manager.approve_request(machine_code, expire_hours)
        
        if success:
            print(f"批准成功: {message}")
            return jsonify({"success": True, "message": message})
        else:
            print(f"批准失败: {message}")
            return jsonify({"success": False, "error": message}), 500
            
    except Exception as e:
        error_msg = f"批准授权时发生异常: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/api/reject', methods=['POST'])
def api_reject():
    """API: 拒绝授权"""
    try:
        # 获取请求数据
        if not request.is_json:
            return jsonify({"success": False, "error": "请求格式错误，需要JSON数据"}), 400
        
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "请求数据为空"}), 400
        
        machine_code = data.get('machine_code')
        reason = data.get('reason', '授权请求被拒绝')
        
        if not machine_code:
            return jsonify({"success": False, "error": "机器码不能为空"}), 400
        
        print(f"收到拒绝请求: 机器码={machine_code}, 原因={reason}")
        
        # 执行拒绝操作
        success, message = auth_manager.reject_request(machine_code, reason)
        
        if success:
            print(f"拒绝成功: {message}")
            return jsonify({"success": True, "message": message})
        else:
            print(f"拒绝失败: {message}")
            return jsonify({"success": False, "error": message}), 500
            
    except Exception as e:
        error_msg = f"拒绝授权时发生异常: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/api/debug')
def api_debug():
    """API: 调试信息"""
    try:
        debug_info = {
            "timestamp": int(time.time()),
            "formatted_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "processed_requests_count": len(auth_manager.processed_requests),
            "processed_requests_list": list(auth_manager.processed_requests)[:10],  # 只显示前10个
            "gitee_config": {
                "repo": GITEE_REPO,
                "api_base": GITEE_API_BASE,
                "token_length": len(GITEE_TOKEN)
            }
        }
        
        # 尝试直接检查Gitee状态
        try:
            requests_url = f"{GITEE_API_BASE}/repos/{GITEE_REPO}/contents/requests"
            params = {"access_token": GITEE_TOKEN, "_t": int(time.time())}
            response = requests.get(requests_url, params=params, timeout=10)
            
            if response.status_code == 200:
                files = response.json()
                debug_info["gitee_requests_folder"] = {
                    "status": "accessible",
                    "file_count": len(files),
                    "files": [f["name"] for f in files[:5]]  # 前5个文件名
                }
            else:
                debug_info["gitee_requests_folder"] = {
                    "status": "error",
                    "status_code": response.status_code
                }
        except Exception as e:
            debug_info["gitee_requests_folder"] = {
                "status": "exception",
                "error": str(e)
            }
        
        return jsonify({"success": True, "debug_info": debug_info})
        
    except Exception as e:
        return jsonify({"success": False, "error": f"调试信息获取失败: {str(e)}"})

@app.route('/manifest.json')
def manifest():
    """PWA清单文件"""
    return jsonify({
        "name": "移动授权管理",
        "short_name": "授权管理",
        "description": "移动端授权管理系统",
        "start_url": "/",
        "display": "standalone",
        "theme_color": "#C1272D",
        "background_color": "#ffffff",
        "icons": [
            {
                "src": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ccircle cx='50' cy='50' r='40' fill='%23C1272D'/%3E%3Ctext x='50' y='60' text-anchor='middle' fill='white' font-size='30'%3E授%3C/text%3E%3C/svg%3E",
                "sizes": "192x192",
                "type": "image/svg+xml"
            }
        ]
    })

if __name__ == '__main__':
    import os
    print("移动授权管理系统启动中...")
    
    # 创建templates目录
    os.makedirs('templates', exist_ok=True)
    
    # 获取端口（云平台会设置PORT环境变量）
    port = int(os.environ.get('PORT', 5000))
    
    print(f"本地访问: http://localhost:{port}")
    print(f"云平台访问: 部署后会提供公网域名")
    
    # 云环境下不启用debug模式
    debug_mode = os.environ.get('RAILWAY_ENVIRONMENT') != 'production'
    
    app.run(host='0.0.0.0', port=port, debug=debug_mode)