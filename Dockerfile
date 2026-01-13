FROM python:3.11-slim

WORKDIR /app

# 시스템 의존성 설치
# curl-cffi를 빌드하기 위해 필요한 도구들
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# uv 설치
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# pyproject.toml과 uv.lock 복사 (lock 파일이 있으면 더 빠르고 재현 가능한 설치)
COPY pyproject.toml uv.lock ./

# 의존성 설치 (--frozen: lock 파일에 고정, --no-dev: 개발 의존성 제외)
RUN uv sync --frozen --no-dev

# 애플리케이션 코드 복사
COPY app/ ./app/

# 포트 노출
EXPOSE 8080

# 환경변수 설정
ENV PYTHONUNBUFFERED=1

# uv를 사용하여 서버 실행
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
