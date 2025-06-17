import json
import re
import math
from typing import List, Dict
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage

class StoryCreator:

    def __init__(self, 
                 api_key: str,
                 base_url: str = "https://cloud.infini-ai.com/maas/v1",
                 model: str = "deepseek-v3",
                 temperature: float = 0):
        self.llm = ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=temperature
        )
        self.history = {
            "background": "",
            "story_segments": []
        }

    def generate_background(self, framework: str = "") -> str:
        """
        在用户提供的背景框架下生成小说故事背景
        
        Args:
            framework: 用户提供的背景框架，可为空
            
        Returns:
            生成的小说背景
        """
        if framework:
            prompt = f"""你需要基于以下内容生成一个简单的小说故事背景：
{framework}

要求：
1. 你的回复应当仅包含故事背景，不应该出现其它任何与故事背景无关的回复内容；
2. 背景设定需完整但不复杂；
3. 包含时间、地点、主要环境或关键背景元素；
4. 语言简洁，控制在100-150个英文单词，用词不要过于文学化；
5. 保持与框架一致的风格和设定方向；
6. 使用 markdown 格式"""
        else:
            prompt = """你需要生成一个简单的小说故事背景：
要求：
1. 你的回复应当仅包含故事背景，不应该出现其它任何与故事背景无关的回复内容；
2. 包含时间、地点、主要环境或关键背景元素；
3. 语言简洁，控制在100-150个英文单词，用词不要过于文学化；
4. 背景设定完整但不复杂；"""
            
        response = self.llm.invoke([SystemMessage(content="你是一个富有创造力的故事创作者"), 
                                   HumanMessage(content=prompt)])
        background = response.content.strip()
        self.history["background"] = background
        return background
    
    def continue_story(self, word_pool: List[str], end : bool = False) -> str:
        """
        在已知背景和前几段故事的基础上续写故事段落，并使用指定单词
        
        Args:
            word_pool: 可供使用的单词池
            
        Returns:
            新续写的故事段落
        """
        min_count = len(word_pool) // 4
        background = self.history["background"]
        previous_segments = self.history["story_segments"]
        
        # 构建故事上下文
        context = f"背景设定：{background}\n"
        if previous_segments:
            context += "已有的故事段落：\n"
            for i, segment in enumerate(previous_segments, 1):
                context += f"段落{i}: {segment}\n"
                
        if end:
            prompt = f"""请基于以下内容为故事续写一段结尾：
{context}

要求：
1. 你的回复应当仅包含续写的故事内容，不应该出现其它任何与故事无关的回复内容；
2. 续写内容需与已有背景和故事段落连贯；
3. 段落长度控制在150-200个英文单词，用词不要过于文学化；
4. 结尾要能够结束整个故事；
"""
        else:
            prompt = f"""请基于以下内容续写一段故事：
{context}

单词池：{word_pool}

要求：
1. 你的回复应当仅包含续写的故事内容，不应该出现其它任何与故事无关的回复内容；
2. 续写内容需与已有背景和故事段落连贯；
3. 段落中必须包含单词池中至少{min_count}个单词；
4. 你需要自然的使用这些单词，在此基础上最大程度地保持故事的一致性和可读性；
5. 段落长度控制在150-200个英文单词，用词不要过于文学化；
"""
        
        response = self.llm.invoke([SystemMessage(content="你是一个专业的故事续写者"), 
                                   HumanMessage(content=prompt)])
        new_segment = response.content.strip()
        return new_segment
    
    def evaluate_and_improve(self, user_segment: str) -> Dict:
        """
        对用户续写的段落进行评价，指出错误并提供修改意见，然后将修改后的段落加入故事
        
        Args:
            user_segment: 用户续写的故事段落
            
        Returns:
            包含评价结果、修改意见和修改后段落的字典
        """
        background = self.history["background"]
        previous_segments = self.history["story_segments"]
        
        # 构建评价提示
        context = f"背景设定：{background}\n"
        if previous_segments:
            context += "已有的故事段落：\n"
            for i, segment in enumerate(previous_segments, 1):
                context += f"段落{i}: {segment}\n"
        
        prompt = f"""请对用户提供的故事段落进行专业评价：
{context}

用户提供的段落：
{user_segment}

评价要求：
1. 检查语法错误并逐一指出；
2. 识别不地道的英文表达；
3. 提供具体的修改建议；
4. 生成修改后的完整段落，确保与上下文连贯；
5. 评价需详细但清晰，修改需保持原文意思不变；

输出格式为JSON，包含三个字段，每个字段的内容为一个字符串，如果要分条，则用换行符分隔：
{{
    "evaluation": "评价内容，包括语法错误和不地道表达",
    "suggestions": "具体修改建议，分点列出",
    "improved_segment": "修改后的完整段落"
}}"""
        
        response = self.llm.invoke([SystemMessage(content="你是一个专业的英语文学编辑"), 
                                   HumanMessage(content=prompt)])
        content = response.content.strip()
        
        # 提取JSON结果
        start_index = content.find('{')
        end_index = content.rfind('}')
        if start_index == -1 or end_index == -1 or end_index <= start_index:
            raise ValueError("未检测到有效的评价结果JSON结构")
        json_str = content[start_index:end_index+1]
        try:
            result = json.loads(json_str)
        except json.JSONDecodeError:
            raise ValueError("评价结果JSON解析失败")
        
        # 验证结果结构
        required_keys = ["evaluation", "suggestions", "improved_segment"]
        if not all(key in result for key in required_keys):
            raise ValueError("评价结果缺少必要字段")

        return result
    
    def get_full_story(self) -> str:
        """获取完整的故事内容（背景+所有段落）"""
        if not self.history["background"]:
            return "故事背景尚未生成"
            
        story = f"故事背景：\n{self.history['background']}\n\n"
        if not self.history["story_segments"]:
            story += "故事段落尚未开始续写"
        else:
            story += "故事内容：\n"
            for i, segment in enumerate(self.history["story_segments"], 1):
                story += f"段落{i}:\n{segment}\n\n"
                
        return story
    
    def append(self, content: str = ""):
        self.history['story_segments'].append(content)

    def delete_story(self):
        self.history['background'] = ''
        self.history['story_segments'] = []