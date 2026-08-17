FROM python:3.12-slim

WORKDIR /app

# Installera systemberoenden
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Kopiera dependencies och installera
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt || \
    pip install --no-cache-dir streamlit plotly httpx python-dotenv cryptography pypdf reportlab mcp[cli] anthropic

# Kopiera källkod
COPY . .

# Miljövariabler för Streamlit i produktion
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_SERVER_ENABLE_CORS=false
ENV STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=false
ENV SIE_MCP_DEMO=1

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
