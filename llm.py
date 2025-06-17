import json
import re
import math
from typing import List, Dict
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage

class LLM:

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

    def make_sentence(self, key: str, pool: List[str]) -> Dict:
        min_count = math.ceil(len(pool) / 2)
        example = {
            "sentence": "They **deserted** the **dessert** in the **desert**.",
            "translation": "他们把甜品遗弃在沙漠里了。",
            "words_list": ["desert", "dessert", "desert"],
            "occur_list": ["deserted", "dessert", "desert"]
        }
        
        prompt = f"""
你是一个英语教学助手，需要根据给定的关键单词和单词池生成例句。要求如下：
1. 生成一个至少25个单词的英文句子，必须包含关键单词"{key}"（需用**加粗），并且是句子的核心
2. 句子中必须包含单词池中至少{min_count}个单词（也需用**加粗，不能替换近义词）
3. 允许重复使用单词（建议展示不同词义），但关键单词每次出现都必须加粗
4. 使用的单词允许语法变形（复数、三单、过去式等），如果变形，就用**将变形后的完整单词包裹起来（例如 **playing** 正确，**play**ing 错误）
5. 输出格式为JSON，包含四个字段：
- "sentence": 英文句子（关键单词用**包裹）
- "translation": 中文翻译，所有单词必须翻译成中文，且对应关键词的中文不要加粗！
- "words_list": 按出现顺序排列的单词原形列表（包括重复）
- "occur_list": 按出现顺序排列的单词在句中出现形式的列表（包括重复，如果有单词在句首这个列表里面对应单词也要首字母大写）

示例输出：
{json.dumps(example, ensure_ascii=False)}

请为以下参数生成句子：
关键单词：{key}
单词池：{pool}
"""

        while True:
            response = self.llm.invoke([SystemMessage(content="你是一个专业的英语老师"), HumanMessage(content=prompt)])

            # 增强JSON提取逻辑
            content = response.content
            print(content)
            start_index = content.find('{')
            end_index = content.rfind('}')
            if start_index == -1 or end_index == -1 or end_index <= start_index:
                raise ValueError("未检测到有效的JSON结构")
            json_str = content[start_index:end_index+1]
            json_str = json_str.replace('\\n', '').replace('\\t', '').strip()
            result = json.loads(json_str)
            if not all(key in result for key in ["sentence", "translation", "words_list", "occur_list"]):
                continue
            if key not in result.get("words_list", []):
                continue
            sentence = result["sentence"]
            occur_list = result["occur_list"]
            sentence = sentence.replace('*', '')

            # 用于记录当前查找位置
            current_index = 0
            # 存储最终结果的分段列表
            parts = []
            # 记录上次处理结束位置
            last_end = 0
            ok = 1

            for word in occur_list:
                # 创建带单词边界的正则模式
                pattern = re.compile(r'\b' + re.escape(word) + r'\b')
                match = pattern.search(sentence, current_index)
                
                if not match:
                    ok = 0
                    break
                
                start, end = match.start(), match.end()
                
                # 添加非加粗部分
                parts.append(sentence[last_end:start])
                # 添加加粗单词
                parts.append(f"**{sentence[start:end]}**")
                
                # 更新位置指针
                last_end = end
                current_index = end
            if not ok:
                continue
            # 添加剩余部分
            parts.append(sentence[last_end:])
            sentence = ''.join(parts)
            result["sentence"] = sentence
            return result

    def generate_fill_in_blank_exercise(self, word_list: List[str]) -> Dict:
        """
        生成英语单词填空练习题
        :param word_list: 单词列表（原形）
        :return: 包含sentence, translation, answer_list, word_list的字典
        """
        # 构建带示例的prompt
        word_list_str = json.dumps(word_list)
        prompt = f"""
你需要根据给定的英语单词列表生成一个完整的填空练习题。要求如下：
1. 生成一段英语段落（长度约{25*len(word_list)}词），包含{len(word_list)}个空。
2. 生成的段落要reasonable，就是上下文必须给填空的单词充分的语境提示，不能是那种可以填任意同类型词的空。请你保证句子中没别的地方出现需填的单词。
3. 每个空用四个下划线____表示，对应单词列表中的一个单词（顺序任意，允许语法变形，例如复数、三单、过去式、现在进行等）。请你避免____之后连续跟变形词尾，如果有变形词尾，就直接放在答案里。例如不鼓励 she is ____ing (答案 sing)，而建议 she is ____ (答案 singing)。
4. 提供段落的中文翻译（填空处正常翻译）
5. 鼓励语法变形，例如shall->should, shoe->shoes。
6. 输出为JSON格式，包含四个字段：
- "sentence": 英语段落字符串（所填单词顺序任意）
- "translation": 中文翻译字符串
- "answer_list": 填空答案列表（变形后的单词）
- "word_list": 单词原形列表（与输入单词表一一对应，顺序与填空答案相同）
示例（单词表为["keep", "apple"]）：
{{
"sentence": "An ____ a day keeps the doctor away, that's why he ____ eating fruit.",
"translation": "一天一个苹果医生远离我，因此他坚持吃水果。",
"answer_list": ["apple", "keeps"],
"word_list": ["apple", "keep"]
}}

现在请为以下单词表生成内容：
单词表：{word_list_str}
鼓励所填单词语法变形!
"""
     
        messages = [
            SystemMessage(content="你是一个英语教学助手，擅长根据单词列表生成上下文合理的填空练习题。"),
            HumanMessage(content=prompt)
        ]
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # 调用LLM生成响应
                response = self.llm.invoke(messages)
                content = response.content
                
                # 提取JSON部分（处理可能的markdown包装）
                start_idx = content.find('{')
                end_idx = content.rfind('}')
                if start_idx == -1 or end_idx == -1:
                    raise ValueError("未检测到JSON边界")
                    
                json_str = content[start_idx:end_idx+1]
                # 处理常见转义问题
                json_str = re.sub(r'\\"', '"', json_str)
                json_str = re.sub(r'\\n', ' ', json_str)
                
                # 解析JSON
                result = json.loads(json_str)
                print(result)
                
                # 验证关键字段存在
                required_keys = {"sentence", "translation", "answer_list", "word_list"}
                if not all(key in result for key in required_keys):
                    raise KeyError("缺少必要字段")
                
                sentence = result["sentence"]
                answer_list = result["answer_list"]
                parts = sentence.split("____")
                new_parts = [parts[0]]  # 第一个部分（____之前的内容）保持不变

                # 遍历每个答案和对应的后续部分
                for i, ans in enumerate(answer_list):
                    if i + 1 >= len(parts):  # 防止索引越界
                        break
                    s = parts[i + 1]  # 当前____后面的字符串
                    k = min(len(ans), len(s))  # 最大可能匹配长度
                    
                    # 从长到短检查所有可能的后缀匹配
                    for n in range(k, 0, -1):
                        if ans.endswith(s[:n]):  # 检查后缀匹配
                            s = s[n:]  # 删除匹配的后缀部分
                            break
                    
                    new_parts.append(s)  # 添加处理后的部分

                # 重新组合句子（用____连接各部分）
                new_sentence = "____".join(new_parts)

                return {
                    "sentence": new_sentence,
                    "translation": result["translation"],
                    "answer_list": result["answer_list"],
                    "word_list": result["word_list"]
                }
                
            except (json.JSONDecodeError, ValueError, KeyError) as e:
                print(f"解析失败（尝试 {attempt+1}/{max_retries}）: {str(e)}")
                if attempt == max_retries - 1:
                    raise RuntimeError("生成失败，请重试") from e
        return {}
    
    def get_synonyms(self, word):
        # 构建带示例的prompt
        prompt = f"""
你是一个英语语言专家，需要为单词"{word}"提供近义词辨析。请严格按以下要求返回JSON格式结果：
1. 至多三个条目，选最典型的近义词。你选择的近义词必须是在某些情况下可以交换使用或易混的词，而不是含义相关（例如apple-pear）但不很相似的词。
2. 每个条目键是近义词（英文），值是该近义词的详细解释（100-200字）
3. 解释主体得是中文，必须包含：
- 先给出该近义词的中文意思
- 与"{word}"在含义和用法上的主要区别
- 两组对比例句（短句即可）：
    例句1: 使用"{word}"的正确示例
    例句2: 使用该近义词的正确示例
- 说明为什么这两个例句不能互换使用
4. 如果没有常见近义词，返回空JSON对象{{}}
5. 只返回纯JSON，不要任何额外说明

示例（单词"buy"的返回格式）：
{{
"purchase": "作为动词，'purchase'强调正式交易场景，常用于商业和法律语境。与'buy'的核心区别在于：'purchase'暗示更正式、金额更大的交易，而'buy'适用于日常消费。例如：'I need to buy groceries'（日常购物）不能替换为'purchase'，显得过于正式；而'The company purchased a building'（商业收购）用'buy'则不够专业，因为涉及正式产权转移。",
"acquire": "'acquire'指通过努力或过程获得，强调获取方式而非金钱交易。与'buy'的区别在于：'acquire'可用于非实物（如技能），且不必然涉及金钱。例如：'She bought a coffee'（金钱交易）不能替换为'acquire'；而'He acquired programming skills'（学习获得）用'buy'则错误暗示了金钱交易。"
}}

现在请为单词"{word}"生成近义词辨析（注意，不是越多越好）：
"""
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # 调用语言模型
                response = self.llm.invoke([
                    SystemMessage(content="你是一个英语词典编辑专家，擅长精确区分近义词的细微差别。"),
                    HumanMessage(content=prompt)
                ])
                
                # 提取JSON部分
                content = response.content
                start_idx = content.find('{')
                end_idx = content.rfind('}')
                
                if start_idx == -1 or end_idx == -1:
                    return {}  # 没有找到JSON结构
                    
                json_str = content[start_idx:end_idx+1]
                # 处理常见格式问题
                json_str = re.sub(r',\s*}', '}', json_str)  # 修复尾部逗号
                json_str = re.sub(r',\s*]', ']', json_str)
                
                result = json.loads(json_str)
                return result
            
            except (json.JSONDecodeError, TypeError) as e:
                print(f"JSON解析失败（尝试 {attempt+1}/{max_retries}）: {str(e)}")
                if attempt == max_retries - 1:
                    return {}  # 最终返回空字典
        
        return {}  # 安全返回
