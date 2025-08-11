#!/bin/bash
# NAS动画文件自动重命名脚本 (重构版)
# 用法: ./anime_renamer.sh "目录名"

# 颜色函数
get_episode_color() {
    local episode=$1
    local episode_num=$((10#$episode))  # 去掉前导零转换为数字
    
    # 基础RGB值，每集增加固定步长
    local step=20
    local r=$((($episode_num * $step) % 256))
    local g=$((($episode_num * $step * 2) % 256))
    local b=$((($episode_num * $step * 3) % 256))
    
    # 确保颜色足够亮，便于阅读
    if [ $r -lt 100 ]; then r=$((r + 100)); fi
    if [ $g -lt 100 ]; then g=$((g + 100)); fi
    if [ $b -lt 100 ]; then b=$((b + 100)); fi
    
    printf "\033[38;2;%d;%d;%dm" $r $g $b
}

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

# 计算最大文件名长度用于对齐
calculate_max_length() {
    local max_len=0
    for file in "${anime_files[@]}"; do
        local len=${#file}
        if [ $len -gt $max_len ]; then
            max_len=$len
        fi
    done
    echo $max_len
}

# 检查参数
if [ $# -ne 1 ]; then
    echo "用法: ./anime_renamer.sh \"目录路径\""
    echo ""
    echo "注意: 如果路径包含空格或特殊字符，请使用双引号包围"
    echo ""
    echo "示例:"
    echo "  ./anime_renamer.sh \"./动画目录\""
    echo "  ./anime_renamer.sh \"/full/path/to/anime directory\""
    echo "  ./anime_renamer.sh \"/path/with [brackets] & special chars\""
    echo ""
    if [ $# -gt 1 ]; then
        echo "检测到多个参数，可能是路径未用引号包围"
        echo "当前接收到的参数："
        for i in $(seq 1 $#); do
            echo "  参数$i: ${!i}"
        done
    fi
    exit 1
fi

DIRECTORY="$1"

# 检查目录是否存在
if [ ! -d "$DIRECTORY" ]; then
    print_error "目录 '$DIRECTORY' 不存在"
    exit 1
fi

# 获取绝对路径和目录名
DIRECTORY="$(realpath "$DIRECTORY")"
original_dir_name="$(basename "$DIRECTORY")"

print_info "正在处理目录: $DIRECTORY"
print_info "目录名: $original_dir_name"

# 询问是否重命名根目录
read -p "是否需要重命名根目录? (y/n): " rename_root
if [[ "$rename_root" == "y" || "$rename_root" == "Y" ]]; then
    read -p "请输入新的目录名: " new_root_name
    if [ -n "$new_root_name" ] && [ "$new_root_name" != "$original_dir_name" ]; then
        parent_dir="$(dirname "$DIRECTORY")"
        new_directory="$parent_dir/$new_root_name"
        
        mv "$DIRECTORY" "$new_directory" 2>/dev/null
        if [ $? -eq 0 ]; then
            print_success "根目录已重命名: $original_dir_name -> $new_root_name"
            DIRECTORY="$new_directory"
            original_dir_name="$new_root_name"
        else
            print_error "重命名根目录失败"
        fi
    fi
fi

# 获取所有相关文件（视频和字幕）
anime_files=()
ignore_patterns="PV|CD|FONTS|FONT|MENU|NCOP|NCED|SP"

echo ""
print_info "扫描相关文件..."

for file in "$DIRECTORY"/*; do
    if [ -f "$file" ]; then
        filename=$(basename "$file")
        
        # 检查是否为视频或字幕文件
        if [[ "$filename" =~ \.(mkv|mp4|avi|m2ts|ts|ass|srt|ssa|vtt|sub|idx|sup)$ ]]; then
            # 检查是否包含忽略的模式
            if ! echo "$filename" | grep -iE "$ignore_patterns" >/dev/null; then
                # 检查是否包含集数格式
                if echo "$filename" | grep -o '\[[^]]*\]' | grep -E '\[[0-9]{2}\]' >/dev/null; then
                    anime_files+=("$filename")
                fi
            fi
        fi
    fi
done

if [ ${#anime_files[@]} -eq 0 ]; then
    print_warning "未找到符合命名规则的动画和字幕文件（包含集数格式）"
    echo ""
    read -p "是否继续进行目录转移操作? (y/n): " continue_without_rename
    
    if [[ "$continue_without_rename" != "y" && "$continue_without_rename" != "Y" ]]; then
        echo "退出脚本"
        exit 0
    fi
    
    # 设置一些默认值用于后续操作
    anime_name="$original_dir_name"
    
    # 即使没有重命名，也要询问季数
    while true; do
        read -p "请输入这是第几季: " season
        if [[ "$season" =~ ^[0-9]+$ ]] && [ "$season" -gt 0 ]; then
            break
        else
            print_error "请输入有效的正整数"
        fi
    done
    
    season_str=$(printf "S%02d" "$season")
    print_info "将使用目录名作为动画名称: $anime_name"
    print_info "季数: $season_str"
    
    # 跳转到转移部分
    skip_rename=true
else
    skip_rename=false
fi

if [ "$skip_rename" = false ]; then
    print_info "找到 ${#anime_files[@]} 个相关文件（视频+字幕）:"
    for i in "${!anime_files[@]}"; do
        echo "$((i+1)). ${anime_files[i]}"
    done
    
    # 分析第一个文件来确定命名规则
    first_file="${anime_files[0]}"
    echo ""
    print_info "分析文件: $first_file"

    # 提取中括号内容
    temp_file=$(mktemp)
    echo "$first_file" | grep -o '\[[^]]*\]' | sed 's/\[//g' | sed 's/\]//g' > "$temp_file"

    # 读取到数组中
    brackets=()
    while IFS= read -r line; do
        brackets+=("$line")
    done < "$temp_file"
    rm "$temp_file"

    if [ ${#brackets[@]} -eq 0 ]; then
        print_error "无法从文件中提取中括号信息"
        exit 1
    fi

    # 寻找集数
    episode=""
    episode_idx=-1
    for i in "${!brackets[@]}"; do
        if [[ "${brackets[i]}" =~ ^[0-9]{2}$ ]] && [ "${brackets[i]}" -ge 1 ] && [ "${brackets[i]}" -le 99 ]; then
            episode="${brackets[i]}"
            episode_idx=$i
            break
        fi
    done

    if [ -z "$episode" ]; then
        print_error "无法从文件中识别集数"
        exit 1
    fi

    print_info "识别到集数: $episode"

    # 显示所有切分信息（除了集数）
    echo ""
    print_info "解析出的信息:"
    info_list=()
    info_display_idx=1

    for i in "${!brackets[@]}"; do
        if [ $i -ne $episode_idx ]; then
            echo "$info_display_idx. ${brackets[i]}"
            info_list+=("${brackets[i]}")
            ((info_display_idx++))
        fi
    done
    
    # 添加额外选项
    echo "$info_display_idx. 使用目录名作为动画名称: $original_dir_name"
    use_dirname_idx=$info_display_idx
    ((info_display_idx++))
    echo "$info_display_idx. 自定义动画名称"
    custom_idx=$info_display_idx

    # 询问哪个是动画名称
    while true; do
        read -p "请选择哪个是动画名称 (1-$info_display_idx): " choice
        if [[ "$choice" =~ ^[0-9]+$ ]]; then
            if [ "$choice" -ge 1 ] && [ "$choice" -le ${#info_list[@]} ]; then
                # 用户选择了解析出的信息
                anime_name="${info_list[$((choice-1))]}"
                break
            elif [ "$choice" -eq $use_dirname_idx ]; then
                # 用户选择了使用目录名作为动画名称
                anime_name="$original_dir_name"
                break
            elif [ "$choice" -eq $custom_idx ]; then
                # 用户选择了自定义选项
                while true; do
                    read -p "请输入自定义动画名称: " custom_name
                    if [ -n "$custom_name" ]; then
                        anime_name="$custom_name"
                        break
                    else
                        print_error "动画名称不能为空，请重新输入"
                    fi
                done
                break
            else
                print_error "请输入 1 到 $info_display_idx 之间的数字"
            fi
        else
            print_error "请输入有效的数字"
        fi
    done

    print_info "选择的动画名称: $anime_name"

    # 询问季数
    while true; do
        read -p "请输入这是第几季: " season
        if [[ "$season" =~ ^[0-9]+$ ]] && [ "$season" -gt 0 ]; then
            break
        else
            print_error "请输入有效的正整数"
        fi
    done

    season_str=$(printf "S%02d" "$season")
    print_info "季数格式: $season_str"

    # 生成重命名预览 - 使用视频文件作为基准创建映射
    echo ""
    echo "==================== 重命名预览 ===================="
    
    # 第1步：扫描所有视频文件创建基础映射
    video_files=()
    rename_map=()  # 存储 "原始基础名|新基础名" 的映射关系
    
    print_info "第1步：扫描视频文件创建基础映射..."
    
    for file in "${anime_files[@]}"; do
        filename=$(basename "$file")
        
        # 只处理视频文件
        if [[ "$filename" =~ \.(mkv|mp4|avi|m2ts|ts)$ ]]; then
            # 提取当前文件的集数
            temp_file2=$(mktemp)
            echo "$filename" | grep -o '\[[^]]*\]' | sed 's/\[//g' | sed 's/\]//g' > "$temp_file2"
            
            current_brackets=()
            while IFS= read -r line; do
                current_brackets+=("$line")
            done < "$temp_file2"
            rm "$temp_file2"
            
            current_episode=""
            
            for bracket in "${current_brackets[@]}"; do
                if [[ "$bracket" =~ ^[0-9]{2}$ ]] && [ "$bracket" -ge 1 ] && [ "$bracket" -le 99 ]; then
                    current_episode="$bracket"
                    break
                fi
            done
            
            if [ -n "$current_episode" ]; then
                # 获取去掉最后扩展名的基础文件名
                base_name="${filename%.*}"
                new_base_name="${anime_name} ${season_str}E${current_episode}"
                
                rename_map+=("$base_name|$new_base_name")
                video_files+=("$filename")
                
                print_info "  映射: $base_name → $new_base_name"
            fi
        fi
    done
    
    if [ ${#rename_map[@]} -eq 0 ]; then
        print_error "未找到任何视频文件来创建基础映射"
        exit 1
    fi
    
    # 第2步：基于映射查找所有相关文件并生成重命名预览
    echo ""
    print_info "第2步：查找所有相关文件并生成重命名预览..."
    
    all_files_in_dir=()
    for file in "$DIRECTORY"/*; do
        if [ -f "$file" ]; then
            all_files_in_dir+=("$(basename "$file")")
        fi
    done
    
    final_rename_list=()
    
    # 计算对齐长度
    max_length=0
    
    for mapping in "${rename_map[@]}"; do
        old_base="${mapping%|*}"
        new_base="${mapping#*|}"

        # 查找所有以这个基础名开头的文件
        for file in "${all_files_in_dir[@]}"; do
            # 检查文件是否完全匹配old_base或以old_base开头后跟点号
            if [[ "$file" == "$old_base" || "$file" == "$old_base."* ]]; then
                # 如果文件名长于old_base，说明有后缀
                if [[ ${#file} -gt ${#old_base} ]]; then
                    # 直接截取old_base之后的部分作为后缀
                    suffix="${file:${#old_base}}"
                    new_filename="${new_base}${suffix}"
                else
                    # 文件名就是基础名，没有后缀
                    new_filename="$new_base"
                fi

                # 计算显示长度
                if [ ${#file} -gt $max_length ]; then
                    max_length=${#file}
                fi

                final_rename_list+=("$file|$new_filename")
            fi
        done
    done
    
    # 显示重命名预览
    padding=$((max_length + 5))
    
    for item in "${final_rename_list[@]}"; do
        old_name="${item%|*}"
        new_name="${item#*|}"
        
        # 提取集数用于颜色显示
        episode_num=""
        if [[ "$new_name" =~ S[0-9]{2}E([0-9]{2}) ]]; then
            episode_num="${BASH_REMATCH[1]}"
        fi
        
        if [ -n "$episode_num" ]; then
            episode_color=$(get_episode_color "$episode_num")
            reset=$(reset_color)
            colored_new_name=$(echo "$new_name" | sed "s/E${episode_num}/E${episode_color}${episode_num}${reset}/g")
            printf "%-*s ==> %s\n" "$padding" "$old_name" "$colored_new_name"
        else
            printf "%-*s ==> %s\n" "$padding" "$old_name" "$new_name"
        fi
    done

    echo "====================================================="

    # 询问是否确认重命名
    echo ""
    read -p "确认执行重命名? (y/n): " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo "取消重命名操作"
        exit 0
    fi

    # 开始重命名
    echo ""
    print_info "开始重命名文件..."
    success_count=0

    for item in "${final_rename_list[@]}"; do
        old_name="${item%|*}"
        new_name="${item#*|}"
        
        old_path="$DIRECTORY/$old_name"
        new_path="$DIRECTORY/$new_name"
        
        if mv "$old_path" "$new_path" 2>/dev/null; then
            print_success "$old_name -> $new_name"
            ((success_count++))
        else
            print_error "重命名失败: $old_name"
        fi
    done

    echo ""
    print_success "重命名完成！成功处理了 $success_count 个文件"
    echo "====================================================="
fi  # 这个fi结束了if [ "$skip_rename" = false ]的条件块

# 询问是否转移到其他目录
echo ""
read -p "是否需要转移整个目录到其他位置? (y/n): " move_files
if [[ "$move_files" == "y" || "$move_files" == "Y" ]]; then
    # 提供默认路径选项
    default_path="/mnt/user/hentaidisk/video/anime"
    echo ""
    print_info "可选择的目标路径:"
    echo "1. 使用默认路径: $default_path"
    echo "2. 输入自定义路径"
    
    read -p "请选择 (1/2): " path_choice
    
    if [[ "$path_choice" == "1" ]]; then
        target_dir="$default_path"
        print_info "使用默认路径: $target_dir"
    else
        read -p "请输入目标目录路径: " target_dir
    fi
    
    # 检查目标目录是否存在，不存在则创建
    if [ ! -d "$target_dir" ]; then
        read -p "目标目录不存在，是否创建? (y/n): " create_dir
        if [[ "$create_dir" == "y" || "$create_dir" == "Y" ]]; then
            mkdir -p "$target_dir"
            if [ $? -eq 0 ]; then
                print_success "目标目录创建成功: $target_dir"
            else
                print_error "目标目录创建失败"
                exit 1
            fi
        else
            echo "取消转移操作"
            exit 0
        fi
    fi
    
    # 构建TMDB层级结构的目标路径
    anime_target_dir="$target_dir/$anime_name"
    season_target_dir="$anime_target_dir/Season $season"
    
    # 检查动画目录是否已存在
    if [ ! -d "$anime_target_dir" ]; then
        mkdir -p "$anime_target_dir"
        print_info "创建动画目录: $anime_target_dir"
    fi
    
    # 检查季目录是否已存在
    if [ -d "$season_target_dir" ]; then
        print_warning "季目录已存在: $season_target_dir"
        read -p "是否覆盖? (y/n): " overwrite
        if [[ "$overwrite" != "y" && "$overwrite" != "Y" ]]; then
            echo "取消转移操作"
            exit 0
        else
            print_info "删除现有季目录..."
            rm -rf "$season_target_dir"
        fi
    fi
    
    # 创建季目录
    mkdir -p "$season_target_dir"
    print_info "创建季目录: $season_target_dir"
    
    # 转移文件到季目录
    echo ""
    print_info "开始转移文件到TMDB结构: $season_target_dir"
    
    # 转移所有内容到季目录
    moved_count=0
    for item in "$DIRECTORY"/*; do
        # 跳过 . 和 .. 目录
        [ -e "$item" ] || continue

        filename=$(basename "$item")
        target_path="$season_target_dir/$filename"

        if mv "$item" "$target_path" 2>/dev/null; then
            print_success "转移: $filename"
            ((moved_count++))
        else
            print_error "转移失败: $filename"
        fi
    done
    
    # 删除空的原目录
    if [ $moved_count -gt 0 ]; then
        rmdir "$DIRECTORY" 2>/dev/null
        if [ $? -eq 0 ]; then
            print_success "删除空的原目录: $DIRECTORY"
        fi
    fi
    echo "======================================================="
    
    print_success "文件转移完成！成功转移了 $moved_count 个文件"
    print_info "TMDB结构路径: $season_target_dir"
    
    # 更新DIRECTORY变量为新的动画根目录（用于后续硬链接调用）
    FINAL_ANIME_DIR="$(realpath "$anime_target_dir")"
    
    # 显示转移后的TMDB结构
    echo ""
    echo "==================== TMDB结构预览 ===================="
    echo "$anime_name/"
    echo "└── Season $season/"
    for file in "$season_target_dir"/*; do
        if [ -f "$file" ]; then
            filename=$(basename "$file")
            echo "    ├── $filename"
        fi
    done
    echo "======================================================="
else
    # 如果不转移，需要创建TMDB结构在原地
    print_info "在原地创建TMDB结构..."
    
    # 创建临时目录来重组文件
    temp_dir=$(mktemp -d)
    season_dir="$temp_dir/Season $season"
    mkdir -p "$season_dir"
    
    # 移动文件到临时季目录
    for file in "$DIRECTORY"/*; do
        if [ -f "$file" ]; then
            filename=$(basename "$file")
            mv "$file" "$season_dir/$filename"
        fi
    done
    
    # 将临时季目录移回原目录
    mv "$season_dir" "$DIRECTORY/"
    rmdir "$temp_dir"
    
    FINAL_ANIME_DIR="$(realpath "$DIRECTORY")"
    
    print_success "本地TMDB结构创建完成"
    print_info "结构路径: $DIRECTORY/Season $season"
    
    # 显示本地TMDB结构
    echo ""
    echo "==================== TMDB结构预览 ===================="
    echo "$(basename "$DIRECTORY")/"
    echo "└── Season $season/"
    for file in "$DIRECTORY/Season $season"/*; do
        if [ -f "$file" ]; then
            filename=$(basename "$file")
            echo "    ├── $filename"
        fi
    done
    echo "======================================================="
fi

# 询问是否创建硬链接
echo ""
read -p "是否创建硬链接? (y/n): " create_hardlink
if [[ "$create_hardlink" == "y" || "$create_hardlink" == "Y" ]]; then
    # 检查hardlink_creator.sh的多个可能位置
    script_dir=$(dirname "$0")
    current_dir=$(pwd)
    
    # 可能的脚本位置
    possible_locations=(
        "$script_dir/hardlink_creator.sh"          # 与anime_renamer.sh同一目录
        "$current_dir/hardlink_creator.sh"         # 当前工作目录
        "./hardlink_creator.sh"                    # 相对路径
        "$(dirname "$0")/hardlink_creator.sh"      # 脚本所在目录
    )
    
    hardlink_script=""
    
    # 查找hardlink_creator.sh
    for location in "${possible_locations[@]}"; do
        if [ -f "$location" ]; then
            hardlink_script="$location"
            break
        fi
    done
    
    if [ -n "$hardlink_script" ]; then
        print_info "找到硬链接脚本: $hardlink_script"
        print_info "调用硬链接创建脚本..."
        echo "执行命令: \"$hardlink_script\" \"$FINAL_ANIME_DIR\""
        
        # 调用硬链接脚本
        bash "$hardlink_script" "$FINAL_ANIME_DIR"
    else
        print_error "未找到 hardlink_creator.sh"
        print_info "已检查以下位置:"
        for location in "${possible_locations[@]}"; do
            echo "  - $location"
        done
        print_info "请手动运行: hardlink_creator.sh \"$FINAL_ANIME_DIR\""
    fi
else
    print_info "跳过硬链接创建"
    print_info "如需后续创建硬链接，请运行: hardlink_creator.sh \"$FINAL_ANIME_DIR\""
fi

print_success "动画重命名脚本执行完成！"
exit 0
# 结束脚本