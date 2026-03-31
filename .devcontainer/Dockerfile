FROM ubuntu:26.04

# Install common utilities
RUN apt-get update && apt-get install -y \
    python-is-python3 \
    python3-dev \
    pipx \
    bash \
    curl \
    findutils \
    git \
    unzip \
    npm \
    nodejs \
    libtree-sitter-dev \
    build-essential \
    mkdocstrings \
    && rm -rf /var/lib/apt/lists/*

USER ubuntu

# Install opencode
RUN npm config set prefix '~/.local/'
RUN npm i -g opencode-ai@latest
RUN mkdir -p ~/.local/share/opencode

# Install tree-sitter CLI
RUN npm i -g tree-sitter-cli@latest

# Install Poetry
RUN pipx install poetry
RUN pipx ensurepath

# Set working directory
WORKDIR /workspace

# Copy the rest of the code
COPY . /workspace

# Default shell
CMD ["bash"]