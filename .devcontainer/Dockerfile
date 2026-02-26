FROM ubuntu:26.04

# Install common utilities
RUN apt-get update && apt-get install -y \
    python-is-python3 \
    pipx \
    bash \
    curl \
    findutils \
    git \
    unzip \
    npm \
    libtree-sitter-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

USER ubuntu

# Install opencode
RUN npm config set prefix '~/.local/'
RUN npm i -g opencode-ai@latest
RUN mkdir -p ~/.local/share/opencode

# Install Poetry
RUN pipx install poetry
RUN pipx ensurepath

# Set working directory
WORKDIR /workspace

# Copy the rest of the code
COPY . /workspace

# Default shell
CMD ["bash"]