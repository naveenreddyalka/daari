# r/LocalLLaMA draft

Flair: Resources or Showcase. You post; do not use a bot.

**Title**

daari: local-first router in front of Cursor — cache and Ollama before any frontier call

**Text**

For people already running Ollama and still watching Cursor dump the same prompt at a frontier API:

daari is a localhost router (OpenAI + Anthropic compatible). Path is cache → tools → your local models → cloud last. Second identical request is an L0 cache hit. There is a measured false-hit rate, not just cosine.

```
pip install daari && ollama pull llama3.2:3b && daari serve
```

Docs: https://naveenreddyalka.github.io/daari/  
Repo: https://github.com/naveenreddyalka/daari  
Same-machine bench vs LiteLLM: https://naveenreddyalka.github.io/daari/developer/resources/benchmark-vs-litellm/

Apache 2.0 (OSI open source).

I use it as the Cursor base URL. What would make this useful on your box?
