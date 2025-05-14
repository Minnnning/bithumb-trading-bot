#!/bin/bash

# 기존 bot-container가 있으면 강제 삭제
if docker ps -a --format '{{.Names}}' | grep -Eq "^bot-container\$"; then
  echo "Removing existing bot-container..."
  docker rm -f bot-container
fi

# 이미지 빌드
echo "Building Docker image (bithumb-bot)..."
docker build -t bithumb-bot .

# 컨테이너 실행
echo "Starting bot-container..."
docker run -d --name bot-container bithumb-bot
