FROM python:3.12-slim

WORKDIR /app

# Installera systemberoenden
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Kopiera dependencies och installera.
#
# Reservgrenen är BORTTAGEN 2026-08-29. Den såg ut som robusthet och var ett
# fail-open: när `requirements.txt` föll — vilket den gjorde, eftersom
# quiet-oppen-data hämtas från ett PRIVAT repo och bygget saknade
# GitHub-uppgifter — installerade den en handskriven lista utan
# quiet-oppen-data. Bygget lyckades, avbilden såg frisk ut, och paketet
# saknades. `fraga_myndighetskallor` och Bolagsverket-verktygen var därmed
# trasiga i drift utan att något sa ifrån.
#
# Ett bygge som inte kan installera sina beroenden ska FALLA, inte leverera en
# halv avbild.
#
# quiet_chatt är privat. Ge bygget en läsbehörig GitHub-token som
# BuildKit-hemlighet med id `github_token` — i Coolify under Build → Secrets.
# Hemligheten monteras bara under det här kommandot och hamnar aldrig i ett
# avbildslager (till skillnad från ARG, som ligger kvar i `docker history`).
# Se deploy/DRIFTSATTNING.md.
COPY requirements.txt .
RUN --mount=type=secret,id=github_token,required=false \
    if [ -s /run/secrets/github_token ]; then \
        sed "s|https://github.com/|https://$(cat /run/secrets/github_token)@github.com/|" \
            requirements.txt > /tmp/krav.txt; \
    else \
        cp requirements.txt /tmp/krav.txt; \
    fi && \
    pip install --no-cache-dir -r /tmp/krav.txt && \
    rm -f /tmp/krav.txt

# Beroendekontroll. En avbild utan quiet_oppen_data är trasig och ska inte
# byggas färdigt: felet hör hemma i byggloggen, inte första gången en användare
# ställer en juridikfråga.
RUN python -c "import quiet_oppen_data.adaptrar.bolagsverket" || ( \
        echo "FEL: quiet-oppen-data saknas i avbilden." && \
        echo "quiet_chatt ar ett privat repo - satt BuildKit-hemligheten github_token." && \
        echo "Se deploy/DRIFTSATTNING.md, avsnitt 'Den privata beroendekedjan'." && \
        exit 1 )

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
