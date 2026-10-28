# Aravind AI

A lightweight AI chat app with a static HTML frontend and a Python serverless API for OpenRouter.

## Deploy to Vercel

1. Push this project to a GitHub repository. Do not commit `.env`; it is ignored by Git.
2. In Vercel, choose **Add New → Project** and import the repository.
3. Before deploying, add this project environment variable in **Settings → Environment Variables**:
   - Name: `OPENROUTER_API_KEY`
   - Value: your OpenRouter API key
   - Environments: select the environments you plan to use.
4. Deploy the project. Vercel serves `Ai.html` at `/` and deploys `api/chat.py` as `/api/chat`.
5. After changing the environment variable, create a new deployment for the change to take effect.

Set a usage limit on the OpenRouter key. The chat API is public and does not include user accounts or authentication, so anyone who can access the deployed site can submit prompts using your key.

## Run locally

1. Copy `.env.example` to `.env` and add your OpenRouter API key.
2. Double-click `Start-Aravind-AI.bat`.
3. Open `http://127.0.0.1:8000`.

The local Python server and the Vercel function share the same OpenRouter client logic in `server.py`. Chat history is stored in the browser's local storage; it is not synchronized between browsers or devices.
