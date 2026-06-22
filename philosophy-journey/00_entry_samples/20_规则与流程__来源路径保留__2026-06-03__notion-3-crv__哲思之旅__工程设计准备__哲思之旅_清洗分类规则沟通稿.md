# 哲思之旅｜清洗与分类规则沟通稿

生成时间：2026-06-09

## 1. 先说总原则

原始母本不删。  
我们只在“哲学工程工作副本”里删生活日志、删非哲学内容、分问题角色、挂哲学坐标。

这样做有两个好处：

- 原文永远完整保留，可以回源。
- 哲学工程只处理哲学问题，不被生活流水淹没。

## 2. 生活内容怎么删

进入剔除清单的内容：

- 旅行路线、吃住行、日常流水。
- 纯生活日志，没有哲学问题。
- 纯人物往来，没有升格为伦理、认识、审美、生命意义等问题。
- 只是在记录事件，没有追问、没有概念、没有思想判断。

不进入剔除清单的生活材料：

- 生活事件直接引出“意义、死亡、真幻、责任、同意、审美、AI 记忆、主体连续性”等哲学问题。
- 生活材料虽然不是问句，但已经形成哲学命题，比如“聊天页面为什么不能成为固定源文件”这种技术认识论问题。

所以不是按“有没有生活细节”判断，而是按“是否进入哲学问题”判断。

## 3. 提问怎么分

以后固定分三条线：

1. 本人提问主线  
   这是工程核心。你的问题是原点，后续哲学学习都从这里出发。

2. AI 追问辅助线  
   AI 提出来的追问可以保留，但只能做辅助，不能替代你的原始问题。

3. 待复核角色线  
   因为原文不是标准聊天导出，有些段落分不清是谁说的，先放这里，后续人工判断。

非提问的哲学化评论，不进问题主线，放入“哲学论述素材旁库”。

## 4. 目前已经生成的结果

原文自然段：12653 段。

清洗后：

- 哲学问题/哲学内容工作副本：2917 段
- 剔除或旁置生活日志与非哲学段：9736 段
- 本人提问主线：230 条
- AI 追问辅助线：116 条
- 待复核角色问题：47 条
- 哲学论述素材旁库：2524 条

这说明第一轮已经把生活内容大幅压下去了。下一轮应继续做“人工复核式精洗”：把误入主线的 AI 句子剔掉，把真正属于你的哲学问题定名。

## 5. 哲学分类底座从哪里来

分类底座不是我自己编的。采用公开哲学索引与大学哲学研究领域作为来源。

主底座：PhilPapers Categories  
PhilPapers 的分类页说明其有 4500 多个分类，从 broad areas 到 narrow subtopics。它列出的大类包括 Value Theory、Philosophical Traditions，并列出 Applied ethics、Epistemology、History of Western Philosophy、Meta-ethics、Metaphysics、Normative ethics、Philosophy of language、Philosophy of mind、Philosophy of religion、Science Logic and Mathematics 等。

来源：https://philpapers.org/categories.pl

校验底座：Stanford Philosophy Research Overview  
Stanford 哲学系列出的研究领域包括 Metaphysics、Epistemology、Philosophy of Language、Philosophy of Mind、Ethics、Applied Ethics、Political Philosophy、History of Philosophy、Logic、Formal Philosophy、Philosophy of Action、Philosophy of Science。

来源：https://philosophy.stanford.edu/research/research-overview

细分参照：Internet Encyclopedia of Philosophy  
IEP 的分类包括 Value Theory、Metaphysics & Epistemology 等，并作为专业哲学百科提供伦理学、形而上学、认识论等主题文章。

来源：

- https://iep.utm.edu/category/value/
- https://iep.utm.edu/category/m-and-e/

## 6. 本工程采用的哲学坐标

根据上述来源，压缩成 10 个可操作坐标：

1. 本体论/形而上学
2. 认识论
3. 心灵哲学/意识哲学
4. 伦理学
5. 美学
6. 社会/政治哲学
7. 技术哲学/AI哲学
8. 哲学史/人物线
9. 中国/亚洲哲学与宗教哲学
10. 元哲学/学习方法论

为什么这样压缩：

- PhilPapers 是全量底座，适合做坐标来源。
- Stanford 的研究领域清晰，适合做一级目录校验。
- IEP 方便后续给每个概念找入门文章。
- 你的文本有强烈的 AI、数字生命、生命经验、爱欲、审美、伦理、真幻问题，所以需要在传统分类上增加“技术哲学/AI哲学”和“元哲学/学习方法论”。

## 7. 后续正式建库时怎么做

第一步：锁定本人提问主线。

只从 `哲思之旅_本人提问主线_v1.csv` 开始，逐条复核：

- 是不是你的问题？
- 是不是哲学问题？
- 是否应合并到前后节点？
- 标题是否准确？
- 归类是否正确？

第二步：AI 追问辅助线回挂。

AI 的追问不做主线，只挂到相关本人问题下面：

- 作为“AI 引出的下一问”。
- 作为“可选追问”。
- 作为“需要警惕的 AI 诱导问题”。

第三步：生成哲学问题卡。

每个本人问题变成一张卡：

- 原文
- 清洗后的问题
- 哲学升格
- 分类坐标
- 相关人物
- 相关经典
- 反方问题
- 下一轮追问

第四步：按地图做学习。

不是按原文顺序一口气学完，而是两条线并行：

- 生命追问线：保留你从一个问题到下一个问题的自然路径。
- 哲学地图线：把问题挂到本体论、认识论、伦理学、美学等坐标里。

## 8. 我建议的下一步

下一步正式执行：

1. 建立 `02_问题母链库`。
2. 只导入 `本人提问主线 v1`。
3. 每 20 条为一批，生成“人工复核小表”。
4. 第一批先复核 1-20 条，定出样板。
5. 样板通过后，再批量清洗后面的 210 条。

这样最稳。先把“问题母链”的口径定准，后面哲学地图、人物、经典、论文都会顺。
