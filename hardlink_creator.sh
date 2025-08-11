#!/bin/bash

# 硬链接创建脚本 (TMDB结构专用)
# 用法: ./hardlink_creator.sh "动画根目录" [目标目录]
# 期望输入目录结构：
# 动画名/
# ├── Season 1/
# │   ├── 动画名 S01E01.mkv
# │   ├── 动画名 S01E01.ass
# │   └── ...
# └── Season 2/
#     ├── 动画名 S02E01.mkv
#     └── ...

# 重置颜色
reset_color() {
    printf "\033[0m"
}

print_success() {
    printf "\033[32m✓ %s\033[0m\n" "$1"
}

print_error() {
    printf "\033[31m✗ %s\033[0m\n" "$1"
}

print_info() {
    printf "\033[36m%s\033[0m\n" "$1"
}

print_warning() {
    printf "\033[33m⚠ %s\033[0m\n" "$1"
}

DIRECTORY="$1"
# 检查目录是否存在
if [ ! -d "$DIRECTORY" ]; then
    print_error "目录 '$DIRECTORY' 不存在"
    exit 1
fi
ANIME_ROOT_DIR="$DIRECTORY"
anime_name=$(basename "$DIRECTORY")
print_info "正在处理目录: $DIRECTORY"
print_info "动画名: 《$anime_name》"


# 如果没有提供目标目录，询问用户
if [ -z "$TARGET_DIR" ]; then
    echo ""
    print_info "选择目标目录:"
    echo "1. 使用默认路径: /mnt/user/hentaidisk/video/link/anime/动漫"
    echo "2. 输入自定义路径"
    
    read -p "请选择 (1/2): " path_choice
    
    if [[ "$path_choice" == "1" ]]; then
        TARGET_DIR="/mnt/user/hentaidisk/video/link/anime/动漫"
        print_info "使用默认路径: $TARGET_DIR"
    else
        read -p "请输入目标目录路径: " TARGET_DIR
    fi
fi

print_info "目标目录: $TARGET_DIR"

# 检查目标目录是否存在，不存在则创建
if [ ! -d "$TARGET_DIR" ]; then
    read -p "目标目录不存在，是否创建? (y/n): " create_target
    if [[ "$create_target" == "y" || "$create_target" == "Y" ]]; then
        mkdir -p "$TARGET_DIR"
        if [ $? -eq 0 ]; then
            print_success "目标目录创建成功: $TARGET_DIR"
        else
            print_error "目标目录创建失败"
            exit 1
        fi
    else
        echo "取消硬链接操作"
        exit 0
    fi
fi

# 创建目标动画根目录
target_anime_dir="$TARGET_DIR/$anime_name"
if [ ! -d "$target_anime_dir" ]; then
    mkdir -p "$target_anime_dir"
    print_info "创建目标动画目录: $target_anime_dir"
fi

# 预览将要创建的硬链接结构
echo ""
echo "==================== 硬链接预览 ===================="
print_info "将创建以下TMDB硬链接结构："
echo "$anime_name/"

# 扫描 Season 目录
season_dirs=()
for dir in "$ANIME_ROOT_DIR"/Season\ [1-9]; do
    if [ -d "$dir" ]; then
        season_dirs+=("$(basename "$dir")")
    fi
done

# 打印扫描到的 Season 目录
echo ""
print_info "共扫描到 ${#season_dirs[@]} 个 Season 目录："

hardlink_plan=()

for season_dir in "${season_dirs[@]}"; do
    season_path="$ANIME_ROOT_DIR/$season_dir"
    target_season_dir="$target_anime_dir/$season_dir"
    
    echo "├── $season_dir/"
    
    # 创建目标季目录（如果不存在）
    if [ ! -d "$target_season_dir" ]; then
        mkdir -p "$target_season_dir"
    fi
    
    # 收集该季的所有有效文件
    for file in "$season_path"/*; do
        if [ -f "$file" ]; then
            filename=$(basename "$file")
            
            # 检查是否为有效的动画文件
            if [[ "$filename" =~ \.(mkv|mp4|avi|m2ts|ts|ass|srt|ssa|vtt|sub|idx|sup)$ ]] && [[ "$filename" =~ S[0-9]{2}E[0-9]{2} ]]; then
                season_number=$(echo "$season_dir" | grep -o '[0-9]\+')
                file_season=$(echo "$filename" | grep -o 'S[0-9]\{2\}' | sed 's/S//')
                expected_season=$(printf "%02d" "$season_number")
                
                if [ "$file_season" = "$expected_season" ]; then
                    echo "│   ├── $filename"
                    hardlink_plan+=("$file|$target_season_dir/$filename")
                fi
            fi
        fi
    done
done

echo "====================================================="
echo "总计将创建 ${#hardlink_plan[@]} 个硬链接"

# 询问是否确认创建硬链接
echo ""
read -p "确认创建硬链接? (y/n): " confirm
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "取消硬链接操作"
    exit 0
fi

# 开始创建硬链接
echo ""
print_info "开始创建硬链接..."
success_count=0
error_count=0
existing_count=0

for item in "${hardlink_plan[@]}"; do
    source_file="${item%|*}"
    target_file="${item#*|}"
    filename=$(basename "$source_file")
    
    # 如果目标文件已存在，检查是否已经是硬链接
    if [ -f "$target_file" ]; then
        source_inode=$(stat -c '%i' "$source_file" 2>/dev/null)
        target_inode=$(stat -c '%i' "$target_file" 2>/dev/null)
        
        if [ "$source_inode" = "$target_inode" ]; then
            print_info "已存在硬链接，跳过: $filename"
            ((existing_count++))
            continue
        else
            # TODO: 添加更智能的重复处理逻辑
            print_warning "目标文件已存在但不是硬链接，强制覆盖: $filename"
            rm -f "$target_file"
        fi
    fi
    
    # 创建硬链接
    if ln "$source_file" "$target_file" 2>/dev/null; then
        print_success "硬链接: $filename"
        ((success_count++))
    else
        print_error "硬链接失败: $filename"
        ((error_count++))
    fi
done

# 显示结果统计
echo ""
echo "==================== 硬链接完成 ===================="
print_success "成功创建: $success_count 个硬链接"
if [ $existing_count -gt 0 ]; then
    print_info "已存在: $existing_count 个硬链接"
fi
if [ $error_count -gt 0 ]; then
    print_error "失败: $error_count 个文件"
fi
print_info "目标位置: $target_anime_dir"

# 显示创建的硬链接目录结构
if [ $success_count -gt 0 ] || [ $existing_count -gt 0 ]; then
    echo ""
    echo "硬链接目录结构:"
    echo "$anime_name/"
    
    for season_dir in "${season_dirs[@]}"; do
        target_season_dir="$target_anime_dir/$season_dir"
        if [ -d "$target_season_dir" ]; then
            echo "├── $season_dir/"
            for file in "$target_season_dir"/*; do
                if [ -f "$file" ]; then
                    filename=$(basename "$file")
                    echo "│   ├── $filename"
                fi
            done
        fi
    done
fi