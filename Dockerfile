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

# pyproject.toml과 uv.lock 복사
# --no-install-project 옵션을 사용하므로 README.md는 필요 없음
COPY pyproject.toml uv.lock ./

# 의존성만 설치 (프로젝트 자체는 설치하지 않음)
# --frozen: lock 파일에 고정
# --no-dev: 개발 의존성 제외
# --no-install-project: 프로젝트 자체를 editable 모드로 설치하지 않음 (빌드 불필요)
RUN uv sync --frozen --no-dev --no-install-project

# 애플리케이션 코드 복사
COPY app/ ./app/

# 포트 노출
EXPOSE 8080

# 환경변수 설정
ENV PYTHONUNBUFFERED=1

# uv를 사용하여 서버 실행
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
