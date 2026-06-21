import re
import os
import shutil
import sys
import httpx

def clean_and_create_dirs():
    print("🧹 Cleaning up old environments...")
    downloads_dir = '/workspaces/anime_triage/regression_downloads/Downloads'
    target_dir = '/workspaces/anime_triage/regression_target'
    
    shutil.rmtree(downloads_dir, ignore_errors=True)
    shutil.rmtree(target_dir, ignore_errors=True)
    
    print("📁 Creating regression target directories...")
    os.makedirs(downloads_dir, exist_ok=True)
    os.makedirs(os.path.join(target_dir, 'mnt/user/hentaidisk/video/anime'), exist_ok=True)
    os.makedirs(os.path.join(target_dir, 'mnt/user/hentaidisk/video/link/Bangumi'), exist_ok=True)
    os.makedirs(os.path.join(target_dir, 'mnt/user/hentaidisk/video/link/anime/动漫'), exist_ok=True)
    os.makedirs(os.path.join(target_dir, 'mnt/user/hentaidisk/video/link/anime/动画电影'), exist_ok=True)

    return downloads_dir

def parse_tree(filename, out_dir):
    print(f"🌳 Parsing {filename} and rebuilding tree into {out_dir}...")
    with open(filename, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    if not lines:
        print("Empty tree file!")
        return
        
    path_stack = []
    current_paths = {}
    paths_with_children = set()
    
    valid_lines = []
    for line in lines[1:]:
        line = line.rstrip('\n')
        if not line or line == '.':
            continue
        if 'directories,' in line and 'files' in line:
            continue
            
        match = re.match(r'^([│├└─\s]*)(.*)$', line)
        if not match:
            continue
            
        prefix = match.group(1)
        name = match.group(2)
        if not name:
            continue
            
        # Each level is exactly 4 characters of indentation in standard tree output
        level = len(prefix) // 4
        valid_lines.append((level, name))

    for i, (level, name) in enumerate(valid_lines):
        while len(path_stack) >= level:
            path_stack.pop()
        path_stack.append(name)
        current_paths[i] = list(path_stack)
        
        # Check if previous item is a parent
        if level > 1:
            parent_idx = i - 1
            while parent_idx >= 0:
                if len(current_paths[parent_idx]) == level - 1:
                    paths_with_children.add(tuple(current_paths[parent_idx]))
                    break
                parent_idx -= 1

    for i, (level, name) in enumerate(valid_lines):
        p_stack = current_paths[i]
        full_path = os.path.join(out_dir, *p_stack)
        if tuple(p_stack) in paths_with_children or not '.' in name:
            os.makedirs(full_path, exist_ok=True)
        else:
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'w') as f:
                f.write('')

if __name__ == '__main__':
    downloads_dir = clean_and_create_dirs()
    parse_tree('unriad.output', downloads_dir)
    print("✅ Regression environment fully reset!")
    
    # Trigger a scan to repopulate the UI correctly
    try:
        print("🔄 Triggering API scan to refresh memory...")
        r = httpx.post("http://localhost:8765/api/scan")
        print("API Response:", r.json())
    except Exception as e:
        print("Could not trigger API scan automatically, please click Refresh in the UI.")
