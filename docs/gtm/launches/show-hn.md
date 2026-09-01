# Show HN draft

Post Tue–Thu morning America/New_York. You post; stay in the thread.

**Title**

Show HN: daari – keep Cursor/Claude Code on local cache and models before frontier APIs

**Text**

I got tired of paying frontier rates for work my laptop can repeat from cache or a small local model.

daari is a local-first execution router. It sits on localhost in front of Cursor, Claude Code, or any OpenAI-compatible client and tries, in order: exact cache → semantic cache → rules/tools → Ollama/MLX → frontier last.

```
pip install daari
ollama pull llama3.2:3b
daari serve
```

Same `curl` twice: the second response is `"tier": "L0"` in `daari_meta`. `daari report` estimates what you did not send to the cloud.

Docs: https://naveenreddyalka.github.io/daari/  
Repo: https://github.com/naveenreddyalka/daari

License is Apache 2.0 (OSI open source).

Happy to answer routing / cache-trust / Cursor BYOK questions here.
