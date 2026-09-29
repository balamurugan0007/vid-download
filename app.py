from flask import Flask, render_template, request, jsonify, send_file, after_this_request
import yt_dlp
import os
import uuid
import threading

app = Flask(__name__)
app.config['DOWNLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'downloads')

if not os.path.exists(app.config['DOWNLOAD_FOLDER']):
    os.makedirs(app.config['DOWNLOAD_FOLDER'])

# Store progress in memory
progress_data = {}

class MyLogger(object):
    def debug(self, msg):
        pass
    def warning(self, msg):
        pass
    def error(self, msg):
        pass

def my_hook(d):
    download_id = d.get('info_dict', {}).get('download_id', 'unknown')
    if d['status'] == 'downloading':
        total = d.get('total_bytes') or d.get('total_bytes_estimate')
        downloaded = d.get('downloaded_bytes', 0)
        speed = d.get('speed', 0)
        
        if total:
            percent = (downloaded / total) * 100
        else:
            percent = 0
            
        progress_data[download_id] = {
            'status': 'downloading',
            'percent': percent,
            'speed': speed,
            'downloaded': downloaded,
            'total': total
        }
    elif d['status'] == 'finished':
        progress_data[download_id] = {
            'status': 'finished',
            'percent': 100
        }

@app.route('/')
def index():
    shared_url = request.args.get('text') or request.args.get('url') or ''
    return render_template('index.html', shared_url=shared_url)

@app.route('/info', methods=['POST'])
def get_info():
    data = request.json
    url = data.get('url')
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    
    try:
        ydl_opts = {
            'quiet': True,
            'skip_download': True,
            'logger': MyLogger(),
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            formats = info.get('formats', [])
            video_options = {}
            audio_options = {}
            
            for f in formats:
                # Video formats
                if f.get('vcodec') != 'none' and f.get('vcodec') is not None:
                    res = f.get('height', 0)
                    if res and res >= 144:
                        ext = f.get('ext', 'mp4')
                        # Prefer mp4
                        if ext == 'mp4':
                            format_id = f.get('format_id')
                            fps = f.get('fps', '')
                            key = f"{res}p"
                            if key not in video_options or (f.get('tbr', 0) > video_options[key].get('tbr', 0)):
                                video_options[key] = {
                                    'id': format_id,
                                    'resolution': f"{res}p",
                                    'ext': ext,
                                    'fps': fps,
                                    'tbr': f.get('tbr', 0),
                                    'size': f.get('filesize', 0) or f.get('filesize_approx', 0)
                                }
                
                # Audio only
                if (f.get('acodec') != 'none' and f.get('acodec') is not None) and (f.get('vcodec') == 'none' or f.get('vcodec') is None):
                    abr = f.get('abr', 0)
                    if abr:
                        key = f"{int(abr)}kbps"
                        if key not in audio_options or (f.get('abr', 0) > audio_options[key].get('abr', 0)):
                            audio_options[key] = {
                                'id': f.get('format_id'),
                                'quality': key,
                                'ext': 'm4a',
                                'abr': abr,
                                'size': f.get('filesize', 0) or f.get('filesize_approx', 0)
                            }
            
            sorted_videos = sorted(video_options.values(), key=lambda x: int(x['resolution'].replace('p', '')), reverse=True)
            sorted_audios = sorted(audio_options.values(), key=lambda x: x['abr'], reverse=True)
            
            return jsonify({
                'title': info.get('title'),
                'thumbnail': info.get('thumbnail'),
                'duration': info.get('duration'),
                'videos': sorted_videos,
                'audios': sorted_audios
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# We use a custom object to pass state into yt-dlp hook
class YtLoggerHook:
    def __init__(self, download_id):
        self.download_id = download_id
    
    def __call__(self, d):
        d['info_dict'] = d.get('info_dict', {})
        d['info_dict']['download_id'] = self.download_id
        my_hook(d)

@app.route('/download', methods=['POST'])
def download():
    data = request.json
    url = data.get('url')
    type_ = data.get('type')
    format_id = data.get('format_id')
    download_id = data.get('download_id')
    
    if not url or not format_id or not download_id:
        return jsonify({'error': 'Missing parameters'}), 400
    
    filename = f"{uuid.uuid4().hex}"
    progress_data[download_id] = {'status': 'starting', 'percent': 0}
    
    hook_obj = YtLoggerHook(download_id)
    
    ydl_opts = {
        'outtmpl': os.path.join(app.config['DOWNLOAD_FOLDER'], filename + '.%(ext)s'),
        'quiet': True,
        'logger': MyLogger(),
        'progress_hooks': [hook_obj],
    }
    
    if type_ == 'audio':
        ydl_opts['format'] = format_id
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
        final_ext = 'mp3'
    else:
        # For video, merge with best audio
        ydl_opts['format'] = f"{format_id}+bestaudio[ext=m4a]/best"
        ydl_opts['merge_output_format'] = 'mp4'
        final_ext = 'mp4'
        
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'video')
            actual_filename = ydl.prepare_filename(info)
            
            if type_ == 'audio':
                actual_filename = os.path.splitext(actual_filename)[0] + '.mp3'
            elif type_ == 'video':
                actual_filename = os.path.splitext(actual_filename)[0] + '.mp4'
                 
            progress_data[download_id]['status'] = 'completed'
            
            return jsonify({
                'success': True,
                'file_path': actual_filename,
                'title': title,
                'ext': final_ext
            })
    except Exception as e:
        progress_data[download_id] = {'status': 'error', 'error': str(e)}
        return jsonify({'error': str(e)}), 500

@app.route('/progress/<download_id>')
def progress(download_id):
    data = progress_data.get(download_id, {'status': 'unknown'})
    return jsonify(data)

@app.route('/download_file')
def download_file():
    path = request.args.get('path')
    title = request.args.get('title')
    ext = request.args.get('ext')
    if path and os.path.exists(path):
        safe_title = "".join([c for c in title if c.isalpha() or c.isdigit() or c==' ']).rstrip()
        if not safe_title:
            safe_title = "download"
            
        @after_this_request
        def remove_file(response):
            try:
                os.remove(path)
            except Exception as e:
                pass
            return response
            
        return send_file(path, as_attachment=True, download_name=f"{safe_title}.{ext}")
    return "File not found", 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
