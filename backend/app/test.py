import asyncio
import subprocess
import requests
from bs4 import BeautifulSoup

def fetch_article_text(url):
    res = requests.get(url)
    soup = BeautifulSoup(res.text, 'html.parser')

    # BBC news article paragraphs are usually in <p> tags inside the article body
    paragraphs = soup.find_all('p')
    article_text = "\n".join(p.get_text() for p in paragraphs)
    return article_text

async def summarize_text(text):
    prompt = f"Summarize this news article in 50 words or less:\n{text}"
    proc = await asyncio.create_subprocess_exec(
        'ollama', 'run', 'llama2:7b-chat',
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout, stderr = await proc.communicate(input=prompt.encode('utf-8'))

    if proc.returncode == 0:
        return stdout.decode().strip()
    else:
        err = stderr.decode()
        raise RuntimeError(f"Ollama CLI error: {err}")

async def main():
    url = "https://www.bbc.com/news/articles/cy8njzr42zvo"
    article_text = fetch_article_text(url)
    summary = await summarize_text(article_text[:2000])  # Limit length if needed
    print("Summary:\n", summary)

asyncio.run(main())
