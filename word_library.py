import json
import random
from typing import List, Dict, Set, Optional
from datetime import datetime

# 单词数据结构定义
WordType = Dict[str, object]  # 单词数据结构：字典类型

class WordLibrary:
    def __init__(self, file_path: str = "word_library.json"):
        self.file_path = file_path
        self.all_words: List[WordType] = self._load_words()
        self.word_ids: Set[str] = set(word["id"] for word in self.all_words)  # 单词ID集合，用于快速查找

    def _load_words(self) -> List[WordType]:
        """从文件加载单词库"""
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 确保数据是列表类型
                if not isinstance(data, list):
                    print(f"警告: 单词库文件格式不正确，期望列表，却得到{type(data)}。重置为新列表。")
                    return []
                return data
        except FileNotFoundError:
            return []

    def save_words(self, new_words: List[WordType] = None):
        """保存单词库（可选：传入新单词列表）"""
        if new_words:
            # 添加新单词（检查ID是否存在）
            for word in new_words:
                if word["id"] not in self.word_ids:
                    self.all_words.append(word)
                    self.word_ids.add(word["id"])
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(self.all_words, f, ensure_ascii=False, indent=2)

    def create_word(self, 
                    word_text: str, 
                    translation: str,
                    pronunciation: Optional[str] = None,
                    example: Optional[str] = None,
                    note: Optional[str] = None) -> WordType:
        """创建新单词对象"""
        return {
            "id": f"word_{datetime.now().timestamp()}",  # 使用时间戳生成唯一ID
            "word": word_text,  # 单词文本
            "translation": translation,  # 翻译
            "pronunciation": pronunciation,  # 发音
            "example": example,  # 例句
            "note": note,  # 笔记
            "created_at": datetime.now().isoformat(),  # 创建时间
            "metadata": {}  # 元数据（可扩展）
        }

    def remove_word(self, word_id: str) -> bool:
        """从单词库中移除指定ID的单词"""
        for i, word in enumerate(self.all_words):
            if word["id"] == word_id:
                del self.all_words[i]
                self.word_ids.remove(word_id)
                self.save_words()  # 立即保存更改
                return True
        return False