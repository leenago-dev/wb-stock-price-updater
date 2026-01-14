FROM python:3.11-slim

WORKDIR /app

# [수정 1] 시스템 의존성 보강 (SSL 관련 라이브러리)
# yfinance 및 기타 네트워크 라이브러리를 위해 SSL 관련 라이브러리가 필요합니다.
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    libssl-dev \
    libcurl4-openssl-dev \
    && rm -rf /var/lib/apt/lists/*

# uv 설치
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 프로젝트 의존성 파일 복사
COPY pyproject.toml uv.lock ./

# 의존성 설치
RUN uv sync --frozen --no-dev --no-install-project

# [수정 2] 가상환경 경로를 시스템 경로(PATH)에 등록
# 이렇게 하면 아래에서 'uv run'을 안 써도 됩니다.
ENV PATH="/app/.venv/bin:$PATH"

# 애플리케이션 코드 복사 (.dockerignore 필수!)
# 이제 app/ 폴더뿐만 아니라 모든 파일을 한 번에 복사합니다.
COPY . .

# 포트 노출
EXPOSE 8080

# 환경변수 설정
ENV PYTHONUNBUFFERED=1

# [수정 3] 실행 명령어 단순화
# 'uv run' 없이 바로 실행 (PATH 설정 덕분에 가능)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
