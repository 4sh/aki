# Dockerfile
# From https://github.com/michaeloliverx/python-poetry-docker-example/blob/master/docker/Dockerfile
# and https://python-poetry.org/docs/faq#poetry-busts-my-docker-cache-because-it-requires-me-to-copy-my-source-files-in-before-installing-3rd-party-dependencies

# builder-base is used to build dependencies
FROM python:3.12-alpine as builder-base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1

RUN apk add curl build-base libffi-dev

WORKDIR /app

# Copy python requirements ans install requirements
COPY pyproject.toml poetry.lock .
RUN pip install poetry && poetry install --only main --no-root --no-directory

# Copy project and reinstall
COPY aki/ ./aki
RUN poetry install --only main

# Remove older files
RUN rm pyproject.toml poetry.lock


FROM python:3.12-alpine as production

# Install aki dependencies
RUN apk add --no-cache docker-cli-compose

COPY --from=builder-base /app /app

ENTRYPOINT /app/.venv/bin/aki $0 $@
CMD ["--help"]
