# r/cursor draft

You post. Reply to setup questions with `daari setup cursor` — do not dump a wall of config.

**Title**

Local router so Cursor stops sending repeat work to frontier APIs

**Text**

If your Cursor bill is mostly “do this again” and “format / classify / small edit”, most of that never needed a frontier model.

daari runs on your machine and becomes the OpenAI-compatible base URL. Cache hits return in milliseconds. Misses go to Ollama (or MLX on Apple Silicon). Frontier is last-resort and optional.

```
pip install daari
daari setup cursor
```

Docs: https://naveenreddyalka.github.io/daari/  
Cursor guide: https://naveenreddyalka.github.io/daari/developer/guides/clients/cursor/  
Repo: https://github.com/naveenreddyalka/daari

License: Apache 2.0.

I am the author. Happy to debug a BYOK / tunnel setup in the comments.
