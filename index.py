# -*- coding: utf-8 -*-
"""
移动端授权管理系统 - Vercel版本
适配Vercel Serverless Functions部署
"""

import os
import json
import time
import hashlib
import requests
from datetime import datetime, timedelta
from urllib.parse import parse_qs

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
            
            timestamp = int(time.time() * 1000)
            random_suffix = f"{timestamp % 10000}"
            
            params = {
                "access_token": GITEE_TOKEN,
                "_t": timestamp,
                "_r": random_suffix,
                "no_cache": "1"
            }
            
            headers = {
                'Cache-Control': 'no-cache, no-store, must-revalidate, max-age=0',
                'Pragma': 'no-cache',
                'Expires': '-1',
                'User-Agent': f'Mobile-Auth-Manager/1.0-{timestamp}',
                'If-None-Match': '*',
                'If-Modified-Since': 'Thu, 01 Jan 1970 00:00:00 GMT'
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=15)
            
            if response.status_code == 200:
                file_info = response.json()
                
                if isinstance(file_info, dict) and 'content' in file_info:
                    content = self._base64_decode(file_info['content'])
                    try:
                        processed_data = json.loads(content)
                        if isinstance(processed_data, list):
                            self.processed_requests = set(processed_data)
                    except json.JSONDecodeError:
                        self.processed_requests = set()
                else:
                    self.processed_requests = set()
            else:
                self.processed_requests = set()
                
        except Exception as e:
            print(f"加载处理记录异常: {e}")
            self.processed_requests = set()
    
    def get_pending_requests(self):
        """获取待处理的授权请求"""
        try:
            self.load_processed_requests()
            
            url = f"{self.api_base}/repos/{GITEE_REPO}/contents/requests"
            timestamp = int(time.time() * 1000)
            random_id = f"{timestamp % 100000}"
            
            params = {
                "access_token": GITEE_TOKEN,
                "_t": timestamp,
                "_r": random_id,
                "no_cache": "1",
                "force_refresh": "1"
            }
            
            headers = {
                'Cache-Control': 'no-cache, no-store, must-revalidate, max-age=0, s-maxage=0, proxy-revalidate',
                'Pragma': 'no-cache',
                'Expires': '-1',
                'User-Agent': f'Mobile-Auth-Manager/1.0-{timestamp}',
                'If-None-Match': '*',
                'If-Modified-Since': 'Thu, 01 Jan 1970 00:00:00 GMT',
                'X-Requested-With': 'XMLHttpRequest'
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=15)
            
            if response.status_code == 200:
                files = response.json()
                pending_requests = []
                
                for file_info in files:
                    if file_info['name'].endswith('.json'):
                        file_content = self._get_file_content(file_info['download_url'])
                        if file_content:
                            try:
                                request_data = json.loads(file_content)
                                current_status = request_data.get('status', 'unknown')
                                
                                if current_status == 'pending':
                                    request_time_str = request_data.get('request_time', '')
                                    try:
                                        request_time = datetime.strptime(request_time_str, '%Y-%m-%d %H:%M:%S')
                                        time_diff = (datetime.now() - request_time).total_seconds()
                                        if 0 <= time_diff <= 86400:  # 24小时内
                                            request_data['file_path'] = file_info['path']
                                            pending_requests.append(request_data)
                                    except Exception:
                                        request_data['file_path'] = file_info['path']
                                        pending_requests.append(request_data)
                            except json.JSONDecodeError:
                                continue
                
                pending_requests.sort(key=lambda x: x.get('request_time', ''), reverse=True)
                return pending_requests
            else:
                return []
                
        except Exception as e:
            print(f"获取请求失败: {e}")
            return []
    
    def approve_request(self, machine_code, expire_hours=720):
        """批准授权请求"""
        try:
            expire_datetime = datetime.now() + timedelta(hours=expire_hours)
            license_code = self._generate_license_code(machine_code, expire_datetime)
            
            if license_code:
                response_data = {
                    "status": "approved",
                    "license_code": license_code,
                    "expire_datetime": expire_datetime.isoformat(),
                    "approve_time": datetime.now().isoformat(),
                    "machine_code": machine_code,
                    "approver": "MobileAuthTool"
                }
                
                success, message = self._upload_response(machine_code, response_data)
                
                if success:
                    self._update_request_status(machine_code, "approved")
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
            response_data = {
                "status": "rejected",
                "message": reason,
                "reject_time": datetime.now().isoformat(),
                "machine_code": machine_code,
                "rejector": "MobileAuthTool"
            }
            
            success, message = self._upload_response(machine_code, response_data)
            
            if success:
                self._update_request_status(machine_code, "rejected")
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
            machine_part = hashlib.sha256(f"MACHINE_{machine_code}_SALT".encode()).hexdigest()[:8].upper()
            date_part = expire_datetime.strftime('%Y%m%d')
            time_part = expire_datetime.strftime('%H%M%S')
            data = f"{machine_code}_{expire_datetime.strftime('%Y%m%d%H%M%S')}_CHECKSUM"
            checksum = hashlib.md5(data.encode()).hexdigest()[:4].upper()
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
            self.processed_requests.add(file_path)
            
            processed_list = list(self.processed_requests)
            content = json.dumps(processed_list, ensure_ascii=False, indent=2)
            
            record_file_path = "processed_requests.json"
            url = f"{self.api_base}/repos/{GITEE_REPO}/contents/{record_file_path}"
            
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
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            
            if response.status_code == 200:
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
                    requests.put(url, json=data, timeout=15)
            else:
                data = {
                    "access_token": GITEE_TOKEN,
                    "content": self._base64_encode(content),
                    "message": f"移动端创建处理记录: {file_path} [{timestamp}]",
                    "branch": "master"
                }
                requests.post(url, json=data, timeout=15)
            
        except Exception as e:
            print(f"标记处理失败: {e}")
    
    def _get_file_content(self, download_url):
        """获取文件内容"""
        try:
            import urllib.parse
            parsed = urllib.parse.urlparse(download_url)
            
            timestamp = int(time.time() * 1000)
            random_suffix = f"{timestamp % 999999}"
            
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
            
            headers = {
                'Cache-Control': 'no-cache, no-store, must-revalidate, max-age=0, s-maxage=0, proxy-revalidate',
                'Pragma': 'no-cache',
                'Expires': '-1',
                'User-Agent': f'Mobile-Auth-Manager/1.0-{timestamp}',
                'If-None-Match': '*',
                'If-Modified-Since': 'Thu, 01 Jan 1970 00:00:00 GMT',
                'X-Requested-With': 'XMLHttpRequest',
                'Connection': 'close'
            }
            
            response = requests.get(new_url, headers=headers, timeout=15)
            if response.status_code == 200:
                return response.text
            else:
                return None
        except Exception as e:
            print(f"获取文件内容异常: {e}")
            return None
    
    def _update_request_status(self, machine_code, new_status):
        """更新请求文件的状态"""
        try:
            request_file_path = f"requests/{machine_code}.json"
            url = f"{self.api_base}/repos/{GITEE_REPO}/contents/{request_file_path}"
            
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
                    original_content = self._base64_decode(file_info['content'])
                    request_data = json.loads(original_content)
                    
                    request_data['status'] = new_status
                    request_data['status_update_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    
                    updated_content = json.dumps(request_data, ensure_ascii=False, indent=2)
                    
                    sha = file_info['sha']
                    update_data = {
                        "access_token": GITEE_TOKEN,
                        "content": self._base64_encode(updated_content),
                        "message": f"移动端更新请求状态: {machine_code} -> {new_status} [{timestamp}]",
                        "sha": sha,
                        "branch": "master"
                    }
                    
                    update_response = requests.put(url, json=update_data, timeout=15)
                    return update_response.status_code == 200
                    
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

# HTML模板
HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <title>移动授权管理</title>
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="default">
    <meta name="apple-mobile-web-app-title" content="授权管理">
    <style>
        * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', sans-serif; margin: 0; padding: 0; background: #f2f2f7; color: #1c1c1e; overflow-x: hidden; }
        .header { background: linear-gradient(135deg, #C1272D 0%, #FF6B35 100%); color: white; padding: 20px 20px 30px 20px; text-align: center; position: sticky; top: 0; z-index: 100; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .header h1 { margin: 0; font-size: 24px; font-weight: 700; }
        .status { margin-top: 10px; font-size: 14px; opacity: 0.9; }
        .container { padding: 20px; max-width: 500px; margin: 0 auto; }
        .request-card { background: white; border-radius: 16px; margin-bottom: 20px; padding: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); border: 1px solid #e5e5ea; transition: transform 0.2s ease; }
        .request-card:active { transform: scale(0.98); }
        .request-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 15px; }
        .machine-code { font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace; font-size: 14px; font-weight: 600; color: #C1272D; background: #fff2f0; padding: 8px 12px; border-radius: 8px; flex: 1; margin-right: 10px; word-break: break-all; }
        .time-badge { background: #007aff; color: white; padding: 4px 8px; border-radius: 12px; font-size: 12px; font-weight: 500; white-space: nowrap; }
        .request-info { margin-bottom: 20px; }
        .info-row { display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 14px; }
        .info-label { color: #8e8e93; font-weight: 500; }
        .info-value { color: #1c1c1e; font-weight: 600; text-align: right; max-width: 60%; word-break: break-all; }
        .action-buttons { display: flex; gap: 12px; }
        .btn { flex: 1; padding: 16px 20px; border: none; border-radius: 12px; font-size: 16px; font-weight: 600; cursor: pointer; transition: all 0.2s ease; position: relative; overflow: hidden; }
        .btn:active { transform: scale(0.95); }
        .btn-approve { background: #34c759; color: white; }
        .btn-approve:hover { background: #30d158; }
        .btn-reject { background: #ff3b30; color: white; }
        .btn-reject:hover { background: #ff453a; }
        .btn:disabled { opacity: 0.6; cursor: not-allowed; transform: none !important; }
        .loading { position: relative; }
        .loading::after { content: ''; position: absolute; top: 50%; left: 50%; width: 20px; height: 20px; margin: -10px 0 0 -10px; border: 2px solid transparent; border-top: 2px solid currentColor; border-radius: 50%; animation: spin 1s linear infinite; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        .empty-state { text-align: center; padding: 60px 20px; color: #8e8e93; }
        .empty-icon { font-size: 48px; margin-bottom: 16px; }
        .refresh-btn { background: #007aff; color: white; border: none; padding: 12px 24px; border-radius: 20px; font-size: 16px; font-weight: 600; cursor: pointer; margin: 20px auto; display: block; transition: background 0.2s ease; }
        .refresh-btn:hover { background: #0056cc; }
        .refresh-btn:active { transform: scale(0.95); }
        .expire-selector { display: flex; gap: 8px; margin-bottom: 15px; justify-content: center; flex-wrap: wrap; }
        .expire-option { background: #f2f2f7; color: #1c1c1e; border: none; padding: 8px 16px; border-radius: 20px; font-size: 13px; font-weight: 500; cursor: pointer; transition: all 0.2s ease; }
        .expire-option.active { background: #007aff; color: white; }
        .expire-option:active { transform: scale(0.95); }
        .toast { position: fixed; top: 100px; left: 50%; transform: translateX(-50%); background: rgba(0, 0, 0, 0.8); color: white; padding: 12px 20px; border-radius: 8px; font-size: 14px; z-index: 1000; opacity: 0; transition: opacity 0.3s ease; }
        .toast.show { opacity: 1; }
        @media (max-width: 375px) { .container { padding: 15px; } .request-card { padding: 16px; } .machine-code { font-size: 12px; } }
        @media (prefers-color-scheme: dark) { body { background: #000000; color: #ffffff; } .request-card { background: #1c1c1e; border-color: #38383a; } .machine-code { background: #2c1810; color: #ff6b47; } .info-label { color: #98989d; } .info-value { color: #ffffff; } .expire-option { background: #2c2c2e; color: #ffffff; } .empty-state { color: #98989d; } }
    </style>
</head>
<body>
    <div class="header">
        <h1>移动授权管理</h1>
        <div class="status" id="statusText">正在加载...</div>
    </div>
    
    <div class="container">
        <div style="display: flex; gap: 10px; margin-bottom: 20px;">
            <button class="refresh-btn" onclick="loadRequests()" style="flex: 1;">刷新请求</button>
            <button class="refresh-btn" onclick="forceSync()" style="flex: 1; background: #ff9500;">强制同步</button>
        </div>
        
        <div id="requestList"></div>
        
        <div id="emptyState" class="empty-state" style="display: none;">
            <div class="empty-icon">📭</div>
            <p>暂无待处理的授权请求</p>
            <p>系统每30秒自动刷新</p>
        </div>
    </div>
    
    <div id="toast" class="toast"></div>
    
    <script>
        let isLoading = false;
        
        function showToast(message) {
            const toast = document.getElementById('toast');
            toast.textContent = message;
            toast.classList.add('show');
            setTimeout(() => { toast.classList.remove('show'); }, 3000);
        }
        
        function formatTime(timeStr) {
            try {
                const date = new Date(timeStr);
                const now = new Date();
                const diff = now - date;
                const minutes = Math.floor(diff / 60000);
                
                if (minutes < 1) return '刚刚';
                if (minutes < 60) return `${minutes}分钟前`;
                
                const hours = Math.floor(minutes / 60);
                if (hours < 24) return `${hours}小时前`;
                
                const days = Math.floor(hours / 24);
                return `${days}天前`;
            } catch {
                return timeStr;
            }
        }
        
        async function loadRequests() {
            if (isLoading) return;
            
            isLoading = true;
            document.getElementById('statusText').textContent = '正在加载请求...';
            
            try {
                const response = await fetch('/api/requests');
                const result = await response.json();
                
                if (result.success) {
                    displayRequests(result.data);
                    document.getElementById('statusText').textContent = 
                        `共 ${result.data.length} 个待处理请求 | ${new Date().toLocaleTimeString()}`;
                } else {
                    throw new Error(result.error || '加载失败');
                }
            } catch (error) {
                console.error('加载请求失败:', error);
                document.getElementById('statusText').textContent = '加载失败，请检查网络';
                showToast('加载失败，请检查网络');
            } finally {
                isLoading = false;
            }
        }
        
        async function forceSync() {
            if (isLoading) return;
            
            isLoading = true;
            document.getElementById('statusText').textContent = '正在强制同步...';
            
            try {
                const response = await fetch('/api/sync', { method: 'POST' });
                const result = await response.json();
                
                if (result.success) {
                    displayRequests(result.data);
                    document.getElementById('statusText').textContent = 
                        `强制同步成功！共 ${result.data.length} 个待处理请求 | ${new Date().toLocaleTimeString()}`;
                    showToast('同步成功');
                } else {
                    throw new Error(result.error || '同步失败');
                }
            } catch (error) {
                console.error('强制同步失败:', error);
                document.getElementById('statusText').textContent = '同步失败，请检查网络';
                showToast('同步失败，请检查网络');
            } finally {
                isLoading = false;
            }
        }
        
        function displayRequests(requests) {
            const listContainer = document.getElementById('requestList');
            const emptyState = document.getElementById('emptyState');
            
            if (requests.length === 0) {
                listContainer.innerHTML = '';
                emptyState.style.display = 'block';
                return;
            }
            
            emptyState.style.display = 'none';
            
            listContainer.innerHTML = requests.map(req => `
                <div class="request-card">
                    <div class="request-header">
                        <div class="machine-code">${req.machine_code}</div>
                        <div class="time-badge">${formatTime(req.request_time)}</div>
                    </div>
                    
                    <div class="request-info">
                        <div class="info-row">
                            <span class="info-label">计算机</span>
                            <span class="info-value">${req.computer_name || 'N/A'}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">用户</span>
                            <span class="info-value">${req.username || 'N/A'}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">系统</span>
                            <span class="info-value">${req.system || 'N/A'}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">请求时间</span>
                            <span class="info-value">${req.request_time}</span>
                        </div>
                    </div>
                    
                    <div class="expire-selector" id="expireSelector_${req.machine_code}">
                        <button class="expire-option active" onclick="setExpireTime('${req.machine_code}', 168)">7天</button>
                        <button class="expire-option" onclick="setExpireTime('${req.machine_code}', 720)">30天</button>
                        <button class="expire-option" onclick="setExpireTime('${req.machine_code}', 2160)">90天</button>
                        <button class="expire-option" onclick="setExpireTime('${req.machine_code}', 8760)">1年</button>
                    </div>
                    
                    <div class="action-buttons">
                        <button class="btn btn-approve" 
                                onclick="approveRequest('${req.machine_code}')"
                                id="approveBtn_${req.machine_code}">
                            批准授权
                        </button>
                        <button class="btn btn-reject" 
                                onclick="rejectRequest('${req.machine_code}')"
                                id="rejectBtn_${req.machine_code}">
                            拒绝授权
                        </button>
                    </div>
                </div>
            `).join('');
        }
        
        function setExpireTime(machineCode, hours) {
            const selector = document.getElementById(`expireSelector_${machineCode}`);
            const options = selector.querySelectorAll('.expire-option');
            
            options.forEach(option => { option.classList.remove('active'); });
            event.target.classList.add('active');
            
            if (!window.expireSelections) {
                window.expireSelections = new Map();
            }
            window.expireSelections.set(machineCode, hours);
        }
        
        async function approveRequest(machineCode) {
            const approveBtn = document.getElementById(`approveBtn_${machineCode}`);
            const rejectBtn = document.getElementById(`rejectBtn_${machineCode}`);
            
            if (approveBtn.disabled) return;
            
            const expireHours = window.expireSelections?.get(machineCode) || 168;
            
            approveBtn.disabled = true;
            rejectBtn.disabled = true;
            approveBtn.classList.add('loading');
            const originalText = approveBtn.textContent;
            approveBtn.textContent = '';
            
            try {
                const response = await fetch('/api/approve', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        machine_code: machineCode,
                        expire_hours: expireHours
                    })
                });
                
                const result = await response.json();
                
                if (result.success) {
                    showToast(`授权成功: ${result.message}`);
                    
                    const requestCard = approveBtn.closest('.request-card');
                    if (requestCard) {
                        requestCard.style.transition = 'all 0.3s ease';
                        requestCard.style.opacity = '0';
                        requestCard.style.transform = 'scale(0.95) translateY(-20px)';
                        
                        setTimeout(() => {
                            requestCard.remove();
                            
                            const remainingCards = document.querySelectorAll('.request-card');
                            if (remainingCards.length === 0) {
                                const emptyState = document.getElementById('emptyState');
                                emptyState.style.display = 'block';
                            }
                        }, 300);
                    }
                    
                    setTimeout(() => { loadRequests(); }, 1000);
                } else {
                    throw new Error(result.error || '未知错误');
                }
            } catch (error) {
                console.error('批准授权失败:', error);
                showToast('批准失败: ' + error.message);
                
                approveBtn.disabled = false;
                rejectBtn.disabled = false;
                approveBtn.classList.remove('loading');
                approveBtn.textContent = originalText;
            }
        }
        
        async function rejectRequest(machineCode) {
            const approveBtn = document.getElementById(`approveBtn_${machineCode}`);
            const rejectBtn = document.getElementById(`rejectBtn_${machineCode}`);
            
            if (rejectBtn.disabled) return;
            
            if (!confirm('确定要拒绝这个授权请求吗？')) {
                return;
            }
            
            approveBtn.disabled = true;
            rejectBtn.disabled = true;
            rejectBtn.classList.add('loading');
            const originalText = rejectBtn.textContent;
            rejectBtn.textContent = '';
            
            try {
                const response = await fetch('/api/reject', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        machine_code: machineCode,
                        reason: '授权请求被移动端管理员拒绝'
                    })
                });
                
                const result = await response.json();
                
                if (result.success) {
                    showToast(`拒绝成功: ${result.message}`);
                    
                    const requestCard = rejectBtn.closest('.request-card');
                    if (requestCard) {
                        requestCard.style.transition = 'all 0.3s ease';
                        requestCard.style.opacity = '0';
                        requestCard.style.transform = 'scale(0.95) translateY(-20px)';
                        
                        setTimeout(() => {
                            requestCard.remove();
                            
                            const remainingCards = document.querySelectorAll('.request-card');
                            if (remainingCards.length === 0) {
                                const emptyState = document.getElementById('emptyState');
                                emptyState.style.display = 'block';
                            }
                        }, 300);
                    }
                    
                    setTimeout(() => { loadRequests(); }, 1000);
                } else {
                    throw new Error(result.error || '未知错误');
                }
            } catch (error) {
                console.error('拒绝授权失败:', error);
                showToast('拒绝失败: ' + error.message);
                
                approveBtn.disabled = false;
                rejectBtn.disabled = false;
                rejectBtn.classList.remove('loading');
                rejectBtn.textContent = originalText;
            }
        }
        
        document.addEventListener('DOMContentLoaded', function() {
            loadRequests();
            setInterval(loadRequests, 30000);
            
            document.addEventListener('visibilitychange', function() {
                if (!document.hidden) {
                    loadRequests();
                }
            });
        });
    </script>
</body>
</html>'''

# Vercel 入口函数
def handler(request):
    """Vercel入口函数"""
    import json
    from urllib.parse import urlparse, parse_qs
    
    # 解析请求
    path = request.url.path if hasattr(request.url, 'path') else '/'
    method = request.method
    query_params = dict(request.query_params) if hasattr(request, 'query_params') else {}
    
    try:
        # 处理不同路由
        if path == '/' or path == '/index.html':
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'text/html; charset=utf-8'},
                'body': HTML_TEMPLATE
            }
        
        elif path == '/api/requests':
            requests_list = auth_manager.get_pending_requests()
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json; charset=utf-8'},
                'body': json.dumps({"success": True, "data": requests_list}, ensure_ascii=False)
            }
        
        elif path == '/api/sync' and method == 'POST':
            auth_manager.load_processed_requests()
            requests_list = auth_manager.get_pending_requests()
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json; charset=utf-8'},
                'body': json.dumps({
                    "success": True, 
                    "message": "同步成功",
                    "data": requests_list,
                    "processed_count": len(auth_manager.processed_requests)
                }, ensure_ascii=False)
            }
        
        elif path == '/api/approve' and method == 'POST':
            body = request.body.decode('utf-8') if hasattr(request, 'body') else '{}'
            data = json.loads(body)
            machine_code = data.get('machine_code')
            expire_hours = data.get('expire_hours', 720)
            
            if not machine_code:
                return {
                    'statusCode': 400,
                    'headers': {'Content-Type': 'application/json; charset=utf-8'},
                    'body': json.dumps({"success": False, "error": "机器码不能为空"}, ensure_ascii=False)
                }
            
            success, message = auth_manager.approve_request(machine_code, expire_hours)
            status_code = 200 if success else 500
            
            return {
                'statusCode': status_code,
                'headers': {'Content-Type': 'application/json; charset=utf-8'},
                'body': json.dumps({"success": success, "message": message}, ensure_ascii=False)
            }
        
        elif path == '/api/reject' and method == 'POST':
            body = request.body.decode('utf-8') if hasattr(request, 'body') else '{}'
            data = json.loads(body)
            machine_code = data.get('machine_code')
            reason = data.get('reason', '授权请求被拒绝')
            
            if not machine_code:
                return {
                    'statusCode': 400,
                    'headers': {'Content-Type': 'application/json; charset=utf-8'},
                    'body': json.dumps({"success": False, "error": "机器码不能为空"}, ensure_ascii=False)
                }
            
            success, message = auth_manager.reject_request(machine_code, reason)
            status_code = 200 if success else 500
            
            return {
                'statusCode': status_code,
                'headers': {'Content-Type': 'application/json; charset=utf-8'},
                'body': json.dumps({"success": success, "message": message}, ensure_ascii=False)
            }
        
        else:
            return {
                'statusCode': 404,
                'headers': {'Content-Type': 'application/json; charset=utf-8'},
                'body': json.dumps({"success": False, "error": "路径不存在"}, ensure_ascii=False)
            }
            
    except Exception as e:
        print(f"处理请求时发生异常: {e}")
        
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json; charset=utf-8'},
            'body': json.dumps({"success": False, "error": f"服务器内部错误: {str(e)}"}, ensure_ascii=False)
        }