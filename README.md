# Tg2Wa-Bridge 
## A Whatsapp, Telegram Bridge 

### Environmental Variables

___(For local/vps deployment rename [.env.sample](.env.sample) to .env and edit with your variable)___.
The sample also contains a brief explanation of what each environmental variable does.


### Deployment:
**With Docker:**
- Install Docker
   - `apt install docker.io -y` _(Debian based systems)_
   - `dnf install docker -y` _(Fedora) (Replace with yum for Centos & other Red hat distros)_
- Clone repository to your preferred location 
- Ensure you are in the proper directory with Dockerfile and .env file present
- Run:
   - `docker build . -t tg2wa`
   - `docker run tg2wa --name wa_bridge`

**Without Docker:**
- Clone repository to your preferred location 
- Install the required dependencies, check the [Dockerfile](Dockerfile) for inspiration.
    - python3.(10 ~ 13), ffmpeg are required
    - Install additional python dependencies with `pip3 install requirements.txt` (Possibly after setting up a venv)
    - Install additional dependencies for sticker conversion to work properly:
        - Download the archive matching your host cpu architecture & platform from [here](https://github.com/ed-asriyan/lottie-converter/releases/).
        (unzip in the same directory this project was cloned to)
        - Download and extract the (webpmux, img2webp) binaries matching your host cpu architecture & platform from [here](https://storage.googleapis.com/downloads.webmproject.org/releases/webp/index.html) and add them to `PATH`. (Preferred archive to download looks like this `libwebp-1.5.0-${platform}-${arch}.tar.gz`)
- Fill the env file.
- Run:
  - `bash run.sh` _To start bot normally_
  - `bash srun.sh` _To start bot silently_


### Commands:
- WA:
    ```
    manage - [Owner] List Manage commands
    tools - [Owner] List tools commands
    ping - Check if bot is alive
    bash - [Dev.] Run bash commands
    eval - [Dev.] Evaluate python commands
    ```
- TG:
    ```
    ping - Check if bot is alive
    bash - [Dev.] Run bash commands
    eval - [Dev.] Evaluate python commands
    ```
### Features:
- Bridges a Whatsapp group with a telegram group
- Subscribe Whatsapp group(s) to a telegram channel.
- Support for edits, deletion and reactions between bridged and subscribed chats.
- Convert a telegram sticker set to Whatsapp sticker pack
- Subscribe to a subreddit:
    - Follow the instructions [here](https://github.com/reddit-archive/reddit/wiki/OAuth2-Quick-Start-Example)
    - Then fill in your CLIENT_ID, SECRET & Reddit Username in the .env (Check the [.env.sample](.env.sample) for the appropriate field names)
