#!/bin/bash

# bot-container가 실행 중인지 확인
container_id=$(docker ps -q --filter "name=bot-container")

if [ -n "$container_id" ]; then
  echo "Stopping bot-container (ID: $container_id)..."
  docker stop "$container_id"
else
  echo "bot-container is not running."
fi
