if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/static/sw.js')
    .catch(err => console.error('Service Worker Failed to Register', err));
}

const urlInput = document.getElementById('url-input');
const fetchBtn = document.getElementById('fetch-btn');
const fetchBtnText = fetchBtn.querySelector('.btn-text');
const fetchBtnLoader = fetchBtn.querySelector('.btn-loader');
const errorMsg = document.getElementById('error-msg');
const videoInfo = document.getElementById('video-info');
const thumbnail = document.getElementById('thumbnail');
const videoTitle = document.getElementById('video-title');
const videoOptions = document.getElementById('video-options');
const audioOptions = document.getElementById('audio-options');
const tabBtns = document.querySelectorAll('.tab-btn');
const progressContainer = document.getElementById('progress-container');
const progressText = document.getElementById('progress-text');
const progressPercent = document.getElementById('progress-percent');
const progressBarFill = document.getElementById('progress-bar-fill');

let currentDownloadId = null;
let progressInterval = null;

if (urlInput.value) {
    fetchInfo(urlInput.value);
}

fetchBtn.addEventListener('click', () => {
    if (urlInput.value) {
        fetchInfo(urlInput.value);
    }
});

tabBtns.forEach(btn => {
    btn.addEventListener('click', (e) => {
        tabBtns.forEach(b => b.classList.remove('active'));
        e.target.classList.add('active');
        const tabId = e.target.dataset.tab;
        document.querySelectorAll('.options-container').forEach(c => c.classList.remove('active-tab'));
        document.getElementById(tabId).classList.add('active-tab');
    });
});

function formatSize(bytes) {
    if (!bytes) return 'Unknown size';
    const mb = bytes / (1024 * 1024);
    return `${mb.toFixed(2)} MB`;
}

function renderOptions(container, items, type) {
    container.innerHTML = '';
    if (!items || items.length === 0) {
        container.innerHTML = '<p style="text-align:center; color:#94a3b8; padding:20px;">No formats found.</p>';
        return;
    }
    
    items.forEach(item => {
        const div = document.createElement('div');
        div.className = 'format-item';
        
        const title = type === 'video' ? `${item.resolution} (MP4)` : `${item.quality} (MP3)`;
        const meta = type === 'video' ? `${item.fps}fps • ${formatSize(item.size)}` : `${formatSize(item.size)}`;
        
        div.innerHTML = `
            <div class="format-info">
                <span class="format-title">${title}</span>
                <span class="format-meta">${meta}</span>
            </div>
            <button class="btn-download-item" data-id="${item.id}" data-type="${type}">Download</button>
        `;
        
        const btn = div.querySelector('.btn-download-item');
        btn.addEventListener('click', () => startDownload(item.id, type));
        
        container.appendChild(div);
    });
}

async function fetchInfo(url) {
    errorMsg.classList.add('hidden');
    videoInfo.classList.add('hidden');
    progressContainer.classList.add('hidden');
    
    fetchBtnText.classList.add('hidden');
    fetchBtnLoader.classList.remove('hidden');
    fetchBtn.disabled = true;
    
    try {
        const res = await fetch('/info', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });
        
        const data = await res.json();
        
        if (data.error) {
            showError(data.error);
        } else {
            thumbnail.src = data.thumbnail;
            videoTitle.textContent = data.title;
            
            renderOptions(videoOptions, data.videos, 'video');
            renderOptions(audioOptions, data.audios, 'audio');
            
            videoInfo.classList.remove('hidden');
        }
    } catch (err) {
        showError('Failed to fetch video information.');
    } finally {
        fetchBtnText.classList.remove('hidden');
        fetchBtnLoader.classList.add('hidden');
        fetchBtn.disabled = false;
    }
}

function showError(msg) {
    errorMsg.textContent = msg;
    errorMsg.classList.remove('hidden');
}

function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

async function startDownload(formatId, type) {
    const url = urlInput.value;
    currentDownloadId = generateUUID();
    
    progressContainer.classList.remove('hidden');
    progressText.textContent = 'Starting download...';
    progressBarFill.style.width = '0%';
    progressPercent.textContent = '0%';
    
    // Disable all download buttons
    document.querySelectorAll('.btn-download-item').forEach(b => b.disabled = true);
    fetchBtn.disabled = true;
    urlInput.disabled = true;
    
    // Start polling
    progressInterval = setInterval(pollProgress, 1000);
    
    try {
        const res = await fetch('/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, format_id: formatId, type: type, download_id: currentDownloadId })
        });
        
        const data = await res.json();
        clearInterval(progressInterval);
        
        if (data.error) {
            progressText.textContent = 'Download Error: ' + data.error;
            progressText.style.color = '#ef4444';
            document.querySelectorAll('.btn-download-item').forEach(b => b.disabled = false);
            fetchBtn.disabled = false;
            urlInput.disabled = false;
        } else {
            progressText.textContent = 'Download Complete! Saving file...';
            progressBarFill.style.width = '100%';
            progressPercent.textContent = '100%';
            
            setTimeout(() => {
                window.location.href = `/download_file?path=${encodeURIComponent(data.file_path)}&title=${encodeURIComponent(data.title)}&ext=${data.ext}`;
                progressContainer.classList.add('hidden');
                document.querySelectorAll('.btn-download-item').forEach(b => b.disabled = false);
                fetchBtn.disabled = false;
                urlInput.disabled = false;
            }, 1500);
        }
    } catch (err) {
        clearInterval(progressInterval);
        progressText.textContent = 'Download failed.';
        document.querySelectorAll('.btn-download-item').forEach(b => b.disabled = false);
        fetchBtn.disabled = false;
        urlInput.disabled = false;
    }
}

async function pollProgress() {
    if (!currentDownloadId) return;
    
    try {
        const res = await fetch(`/progress/${currentDownloadId}`);
        const data = await res.json();
        
        if (data.status === 'downloading') {
            const percent = data.percent.toFixed(1);
            progressBarFill.style.width = `${percent}%`;
            progressPercent.textContent = `${percent}%`;
            
            let speedText = '';
            if (data.speed) {
                const mbps = data.speed / (1024 * 1024);
                speedText = ` (${mbps.toFixed(2)} MB/s)`;
            }
            progressText.textContent = `Downloading...${speedText}`;
        }
    } catch (e) {
        // Ignore polling errors
    }
}
