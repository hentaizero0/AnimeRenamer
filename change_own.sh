#!/bin/bash

# 检查是否提供了目录参数
if [ -z "$1" ]; then
    echo "请提供要修改权限的子目录名称"
    exit 1
fi

# 获取当前目录的子目录
TARGET_DIR="./$1"

# 检查目标目录是否存在
if [ ! -d "$TARGET_DIR" ]; then
    echo "指定的目录 $TARGET_DIR 不存在"
    exit 1
fi

# 修改所有者为 yuyue:users
echo "正在修改所有者为 yuyue:users..."
sudo chown -R yuyue:users "$TARGET_DIR"c'dcd

# 修改权限为 777
echo "正在修改权限为 777..."
sudo chmod -R 777 "$TARGET_DIR"

# # 如果提供了第二个参数，则移动目录
# if [ -n "$2" ]; then
#     DEST_DIR="$2"
    
#     # 检查目标路径是否存在
#     if [ ! -d "$DEST_DIR" ]; then
#         echo "目标目录 $DEST_DIR 不存在"
#         exit 1
#     fi

#     echo "正在将 $TARGET_DIR 移动到 $DEST_DIR..."
#     mv "$TARGET_DIR" "$DEST_DIR"
# fi


echo "操作完成！"
