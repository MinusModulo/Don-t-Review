from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse
import json
import asyncio

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# 模拟LLM服务
class LLM:
    async def generate_sentence(self, word_id):
        # 模拟耗时操作
        await asyncio.sleep(2) 
        return {
            "sentence": "Example sentence for word_id={}".format(word_id),
            "translation": "单词ID={}的翻译".format(word_id),
            "words_list": ["word1", "word2"]
        }

llm = LLM()

@app.get("/learn_word/{word_id}", response_class=HTMLResponse)
async def learn_word(request: Request, word_id: str):
    """返回包含WebSocket客户端的页面"""
    return templates.TemplateResponse("learn_word.html", {
        "request": request,
        "word_id": word_id
    })

@app.websocket("/ws/word/{word_id}")
async def get_sentence_data(websocket: WebSocket, word_id: str):
    """通过WebSocket推送sentence_data"""
    await websocket.accept()
    try:
        # 调用LLM生成数据
        sentence_data = await llm.generate_sentence(word_id)
        # 推送数据到前端
        await websocket.send_text(json.dumps(sentence_data))
    except Exception as e:
        await websocket.send_text(json.dumps({"error": str(e)}))
    finally:
        await websocket.close()