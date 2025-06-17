from fastapi import FastAPI, Request, WebSocket, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from word_library import WordLibrary
from review_manager import ReviewManager
from llm import LLM
from story_creator import StoryCreator
import random
import datetime
import json

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# 初始化依赖
word_library = WordLibrary()
review_manager = ReviewManager(word_library)
API_KEY = str(input("Please enter your infini_ai API_KEY: "))
llm = LLM(api_key=API_KEY)
story_creator = StoryCreator(api_key=API_KEY)

POOL_SIZE = 10
BLANK_SIZE = 5
SYNONYM_SIZE = 1

print("Initialization finished.")
# 路由定义
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """主菜单页面"""
    return templates.TemplateResponse("menu.html", {"request": request})

@app.get("/learn_next_word", response_class=HTMLResponse)
async def learn_next_word(request: Request):
    """学习下一个单词（重定向到合并后的学习页面）"""
    if not review_manager.current_queue:
        new_words = review_manager.init_current_queue()
        if not new_words:
            message = "没有更多新单词可学习！"
            return templates.TemplateResponse("message.html", {"request": request, "message": message})
        message = f"准备学习 {len(new_words)} 个新单词..."
    else:
        message = f"继续学习未完成的 {len(review_manager.current_queue)} 个单词..."

    word_id = review_manager.current_queue[0]
    return RedirectResponse(f"/learn_word/{word_id}")

@app.get("/learn_word/{word_id}", response_class=HTMLResponse)
async def learn_word(request: Request, word_id: str):
    """合并后的单词学习页面，支持显示/隐藏释义"""
    try:
        word = review_manager._get_word_by_id(word_id)
    except ValueError:
        message = f"单词ID {word_id} 不存在！"
        return templates.TemplateResponse("message.html", {"request": request, "message": message})

    return templates.TemplateResponse("learn_word.html", {
        "request": request,
        "word": word,
    })

@app.websocket("/ws/word/{word_id}")
async def get_sentence_data(websocket: WebSocket, word_id: str):
    """通过WebSocket推送sentence_data"""
    await websocket.accept()
    try:
        word = review_manager._get_word_by_id(word_id)
        review_pool = review_manager.select_smart_review_words(POOL_SIZE)
        pool_words = [w["word"] for w in review_pool]
        sentence_data = llm.make_sentence(word["word"], pool_words)
        
        # 获取LLM实际采用的单词ID列表
        used_words = []
        for origin, occur in zip(sentence_data['words_list'], sentence_data['occur_list']):
            match = next((d for d in review_pool if d.get('word') == origin), None)
            if match:
                used_words.append((match['id'], occur))

        # 准备复习池数据，传递给前端
        review_pool_json = json.dumps([{"id": id, "occur": occur} for id, occur in used_words])

        data_package = {
            "review_pool": review_pool_json,
            "sentence_data": sentence_data
        }
        await websocket.send_text(json.dumps(data_package))
    except Exception as e:
        await websocket.send_text(json.dumps({"error": str(e)}))
    finally:
        await websocket.close()

@app.post("/process_learning_choice/{word_id}", response_class=HTMLResponse)
async def process_learning_choice(request: Request, word_id: str):
    """合并处理掌握程度和单词选择的提交"""
    form_data = await request.form()
    
    # print(form_data)

    # 获取掌握程度选择
    choice = form_data.get("choice")
    if not choice:
        return templates.TemplateResponse("message.html", {
            "request": request,
            "message": "请选择对单词的掌握程度",
            "next_url": f"/learn_word/{word_id}"
        })
    choice = int(choice)
    
    # 获取选中的单词
    selected_words_json = form_data.get("selected_words", "[]")
    try:
        selected_words = json.loads(selected_words_json)
    except json.JSONDecodeError:
        selected_words = []

    unselected_words_json = form_data.get("unselected_words", "[]")
    try:
        unselected_words = json.loads(unselected_words_json)
    except json.JSONDecodeError:
        unselected_words = []
    
    # 获取当前单词信息
    try:
        word = review_manager._get_word_by_id(word_id)
    except ValueError:
        return templates.TemplateResponse("message.html", {
            "request": request,
            "message": f"单词ID {word_id} 不存在！",
            "next_url": "/learn_next_word"
        })
    
    # 处理掌握程度选择
    if word_id in review_manager.current_queue:
        review_manager.current_queue.remove(word_id)

    if choice in {1, 2}:
        review_manager.current_queue.append(word_id)
        mastery_message = "这个单词会在稍后的学习中再次出现。"
    elif choice == 3:
        review_manager.process_word(word_id, "keep")
        mastery_message = "太好了！这个单词已被标记为已学习。"
    else:
        mastery_message = "该单词将不会出现在今后的学习中。"
    
    # 处理单词选择（使用前端传递的复习池数据）
    
    # print(f"Now {selected_words}\n{unselected_words}")

    all_remembered = len(selected_words) == 0
    review_manager.process_word_selection(selected_words, unselected_words)
    
    # 保存学习状态
    review_manager.save_learning_state()
    
    # 准备消息
    if all_remembered:
        word_message = "已将所有未标记单词标记为已复习"
    else:
        word_message = f"已标记 {len(selected_words)} 个单词需要重新学习"
    
    # 组合消息
    message = f"{mastery_message}\n{word_message}"
    
    return templates.TemplateResponse("message.html", {
        "request": request,
        "message": message,
        "next_url": "/continue_learning"
    })

@app.get("/continue_learning", response_class=HTMLResponse)
async def continue_learning(request: Request):
    """继续学习页面"""
    if review_manager.current_queue:
        return templates.TemplateResponse("continue_learning.html", {"request": request})
    else:
        message = "已完成所有单词的学习！"
        return templates.TemplateResponse("message.html", {
            "request": request,
            "message": message,
            "next_url": "/"
        })
    
@app.get("/fill_blank_exercise", response_class=HTMLResponse)
async def fill_blank_exercise(request: Request):
    """生成英语单词填空练习页面"""
    try:
        # 选择复习池单词
        review_pool = review_manager.select_smart_review_words(BLANK_SIZE)
        if not review_pool:
            message = "没有更多单词可用于生成练习！"
            return templates.TemplateResponse("message.html", {
                "request": request,
                "message": message,
                "next_url": "/"
            })
            
        pool_words = [w["word"] for w in review_pool]
        
        # 调用LLM生成填空练习
        exercise = llm.generate_fill_in_blank_exercise(pool_words)

        word_list = exercise['word_list']

        review_manager.process_word_selection([], [w['id'] for w in review_pool])

        random.shuffle(word_list)
        
        # 准备模板数据
        context = {
            "request": request,
            "exercise": exercise,
            "word_list": word_list
        }
        
        return templates.TemplateResponse("fill_blank_exercise.html", context)
        
    except Exception as e:
        error_msg = f"生成填空练习失败: {str(e)}"
        print(error_msg)
        return templates.TemplateResponse("message.html", {
            "request": request,
            "message": error_msg,
            "next_url": "/"
        })
    
# 近义词查询页面
@app.get("/synonyms", response_class=HTMLResponse)
async def synonyms_page(request: Request):
    return templates.TemplateResponse("synonyms.html", {"request": request})

# 近义词API
@app.post("/process_synonym_query", response_class=HTMLResponse)
async def process_synonym_query(request: Request):
    form_data = await request.form()
    word = form_data.get("word", "").strip()
    
    if not word:
        return templates.TemplateResponse("synonyms.html", {
            "request": request,
            "error": "请输入英语单词",
            "word": word
        })
    
    try:
        result = llm.get_synonyms(word)
        return templates.TemplateResponse("synonyms.html", {
            "request": request,
            "word": word,
            "synonyms": result,
            "has_result": bool(result)
        })
    except Exception as e:
        return templates.TemplateResponse("synonyms.html", {
            "request": request,
            "word": word,
            "error": f"查询失败: {str(e)}"
        })



# Novelist功能入口
@app.get("/novelist", response_class=HTMLResponse)
async def novelist_home(request: Request):
    """Novelist功能主页"""
    return templates.TemplateResponse("novelist/start.html", {"request": request})

# 故事背景生成页面
@app.get("/novelist/background", response_class=HTMLResponse)
async def background_page(request: Request):
    """故事背景生成页面"""
    story_creator.delete_story()
    return templates.TemplateResponse("novelist/background.html", {
        "request": request,
        "background": story_creator.history["background"]
    })

# 生成故事背景API
@app.post("/api/generate_background", response_class=JSONResponse)
async def generate_background(request: Request):
    """生成故事背景API"""
    try:
        form_data = await request.json()
        framework = form_data.get("framework", "")
        background = story_creator.generate_background(framework)
        return {"success": True, "background": background}
    except Exception as e:
        return {"success": False, "error": str(e)}

# 故事续写页面
@app.get("/novelist/continue", response_class=HTMLResponse)
async def continue_story_page(request: Request):
    """故事续写页面"""
    background = story_creator.history["background"]
    if not background:
        return RedirectResponse("/novelist/background")
        
    segments = story_creator.history["story_segments"]

    review_pool = review_manager.select_smart_review_words(POOL_SIZE)
    if not review_pool:
        message = "没有更多单词可用于生成练习！"
        return templates.TemplateResponse("message.html", {
            "request": request,
            "message": message,
            "next_url": "/"
        })
    pool_words = [w["word"] for w in review_pool]

    return templates.TemplateResponse("novelist/continue.html", {
        "request": request,
        "background": background,
        "segments": segments,
        "word_pool": pool_words
    })

# 加入故事段落
@app.post("/api/ai_append", response_class=JSONResponse)
async def ai_append(request: Request):
    try:
        form_data = await request.json()
        content = form_data.get("segment", "")
        story_creator.append(content)
        return {"success": True, "segment": content}
    except Exception as e:
        return {"success": False, "error": str(e)}

# AI续写故事
@app.post("/api/ai_continue", response_class=JSONResponse)
async def ai_continue_story(request: Request):
    """AI续写故事API"""
    try:
        form_data = await request.json()
        word_pool = form_data.get("word_pool", [])
        is_end = form_data.get("is_end", False)
        segment = story_creator.continue_story(word_pool, is_end)
        return {"success": True, "segment": segment}
    except Exception as e:
        return {"success": False, "error": str(e)}

# 用户续写故事
@app.post("/api/user_continue", response_class=JSONResponse)
async def user_continue_story(request: Request):
    """用户续写故事API"""
    try:
        form_data = await request.json()
        user_segment = form_data.get("segment", "")
        result = story_creator.evaluate_and_improve(user_segment)
        return {"success": True, "evaluation": result}
    except Exception as e:
        return {"success": False, "error": str(e)}

# 显示完整故事
@app.get("/novelist/full_story", response_class=HTMLResponse)
async def full_story_page(request: Request):
    """显示完整故事页面"""
    full_story = story_creator.get_full_story()
    return templates.TemplateResponse("novelist/full_story.html", {
        "request": request,
        "full_story": full_story
    })