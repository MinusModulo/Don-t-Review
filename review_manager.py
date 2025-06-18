import json
import random
from typing import List, Dict, Set
from datetime import datetime
from word_library import WordLibrary, WordType

class ReviewManager:
    def __init__(self, word_lib: WordLibrary, save_path: str = "learning_state.json"):
        self.word_lib = word_lib  # 单词库实例
        self.save_path = save_path  # 学习状态保存路径
        
        # 核心数据结构（存储单词ID而非完整单词对象）
        self.current_queue: List[str] = []  # 今日学习队列（单词ID）
        self.old_queue: List[str] = self._load_learning_state()  # 已学习队列（单词ID）
        self.learned_words: Set[str] = set(self.old_queue)  # 已学习单词ID集合
        
        # 学习统计信息
        self.stats = {
            "total_learned": len(self.learned_words),
            "session_start_time": datetime.now().isoformat(),
            "session_words": 0,
            "session_kept": 0,
            "session_discarded": 0
        }

    def _load_learning_state(self) -> List[str]:
        """加载学习状态"""
        try:
            with open(self.save_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict) and 'old_queue' in data:
                    return data.get('old_queue', [])
                # 兼容旧版本格式
                if isinstance(data, list):
                    return data
                return []
        except FileNotFoundError:
            return []

    def save_learning_state(self):
        """保存学习状态到文件"""
        # 更新统计信息
        self.stats["total_learned"] = len(self.learned_words)
        with open(self.save_path, 'w', encoding='utf-8') as f:
            json.dump({
                "old_queue": self.old_queue,
                "stats": self.stats
            }, f, ensure_ascii=False, indent=2)

    def init_current_queue(self) -> List[WordType]:
        """初始化今日学习队列（随机5个未学习单词）"""
        unlearned = [word for word in self.word_lib.all_words 
                     if word["id"] not in self.learned_words]
        if len(unlearned) < 5:
            selected = unlearned
        else:
            selected = random.sample(unlearned, 5)
        
        # 只存储单词ID到队列
        self.current_queue = [word["id"] for word in selected]
        return selected

    def select_smart_review_words(self, count: int = 10) -> List[WordType]:
        """基于多参数智能选择要复习的单词
        
        评分因素：
        - 复习次数越少，评分越高
        - 距离上次复习时间越久，评分越高
        - 记忆强度越低，评分越高
        """
        if not self.old_queue:
            return []
            
        review_candidates = []
        
        # 计算每个单词的复习评分
        for word_id in self.old_queue:
            try:
                word = self._get_word_by_id(word_id)
            except ValueError as e:
                print(f"警告: {e}，跳过此单词的复习评分计算")
                continue
                
            if "learning_metadata" not in word:
                # 没有学习元数据的单词给予中等评分
                score = 5.0
            else:
                lm = word["learning_metadata"]
                # 1. 复习次数（复习次数越少，越需要复习）
                review_factor = 1.0 / (lm.get("review_count", 1) + 1)
                
                # 2. 时间因素（距离上次复习时间越久，越需要复习）
                last_reviewed = lm.get("last_reviewed")
                if last_reviewed:
                    days_since_review = (datetime.now() - datetime.fromisoformat(last_reviewed)).days
                    time_factor = min(days_since_review / 7, 3.0)  # 最多3倍权重
                else:
                    time_factor = 2.0  # 从未复习过的单词给予较高权重
                
                # 3. 记忆强度（强度越低，越需要复习）
                strength = lm.get("strength", 1.0)
                strength_factor = 1.0 / strength
                
                # 综合评分
                score = review_factor * time_factor * strength_factor
            
            review_candidates.append((word, score))
        
        # 按评分降序排序
        review_candidates.sort(key=lambda x: x[1], reverse=True)
        
        # 随机选择前N个高分单词（避免总是选择相同的单词）
        top_candidates = review_candidates[:min(count*2, len(review_candidates))]
        return [word for word, _ in random.sample(top_candidates, min(count, len(top_candidates)))]

    def process_word(self, word_id: str, action: str):
        """处理单个单词的学习操作"""
        # 不再强制要求单词必须在当前队列中
        # if word_id not in self.current_queue:
        #     raise ValueError("单词不在今日学习队列中")

        # 更新统计信息
        self.stats["session_words"] += 1
        
        # 如果单词在队列中，才移除它
        if word_id in self.current_queue:
            self.current_queue.remove(word_id)

        if action == 'keep':
            self.stats["session_kept"] += 1
            if word_id not in self.old_queue:
                self.old_queue.append(word_id)
            if word_id not in self.learned_words:
                self.learned_words.add(word_id)
                
            # 更新单词学习元数据
            try:
                word = self._get_word_by_id(word_id)
                if "learning_metadata" not in word:
                    word["learning_metadata"] = {
                        "first_learned": datetime.now().isoformat(),
                        "review_count": 0,
                        "last_reviewed": None,
                        "strength": 1
                    }
                
                lm = word["learning_metadata"]
                lm["review_count"] += 1
                lm["last_reviewed"] = datetime.now().isoformat()
                
                if lm["review_count"] >= 3:
                    lm["strength"] = min(lm["strength"] * 1.2, 10.0)
                else:
                    lm["strength"] = min(lm["strength"] * 1.1, 10.0)
                
                self.word_lib.save_words()
            except ValueError as e:
                print(f"警告: {e}，跳过此单词的学习状态更新")
                if word_id in self.old_queue:
                    self.old_queue.remove(word_id)
                self.learned_words.discard(word_id)
        else:
            self.stats["session_discarded"] += 1

    def process_word_selection(self, selected_words, unselected_words):
        """处理用户选择的陌生单词"""

        # 处理选中的需要重新学习的单词
        for word in selected_words:
            # 将选中的单词加入当前学习队列
            if word in self.old_queue:
                self.old_queue.remove(word)
            self.current_queue.append(word)

        # 处理用户记得的单词
        for word_id in unselected_words:
            try:
                # 更新单词的学习元数据
                word = self._get_word_by_id(word_id)
                if "learning_metadata" in word:
                    lm = word["learning_metadata"]
                    lm["review_count"] += 1
                    lm["last_reviewed"] = datetime.now().isoformat()
                    # 轻度增加记忆强度
                    lm["strength"] = min(lm["strength"] * 1.05, 10.0)
                self.word_lib.save_words()
            except ValueError:
                continue

    def is_study_complete(self) -> bool:
        """检查今日学习是否完成"""
        return len(self.current_queue) == 0

    def _get_word_by_id(self, word_id: str) -> WordType:
        """通过ID获取完整单词对象"""
        for word in self.word_lib.all_words:
            if word["id"] == word_id:
                return word
        # 如果单词不在单词库中，尝试从已学习队列中查找
        if word_id in self.old_queue:
            # 从文件重新加载单词库，可能单词被移除后没有更新引用
            self.word_lib.all_words = self.word_lib._load_words()
            for word in self.word_lib.all_words:
                if word["id"] == word_id:
                    return word
                    
            # 如果仍然找不到，可能是单词被意外删除了
            print(f"警告: 单词ID {word_id} 在已学习队列中但不在单词库中，将从学习队列中移除")
            self.old_queue = [wid for wid in self.old_queue if wid != word_id]
            self.learned_words.discard(word_id)
            self.save_learning_state()  # 保存学习状态，移除无效ID
            
        # 如果完全找不到，抛出错误
        raise ValueError(f"单词ID {word_id} 不存在")
