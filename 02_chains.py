"""
第 2 课:LCEL 管道 与 结构化输出

上一课我们直接把字符串扔给模型。但真实应用里,提示词是「模板 + 用户输入」
拼出来的,输出也往往要再加工。LCEL 让你用 | 把这些步骤串成一条流水线。

本课顺带讲 3 个 Python 知识点,标记为 【Python】,遇到就看。
"""

from llm_setup import get_llm

llm = get_llm("qwen-plus", temperature=0.3)

# ═══ 第 1 步:提示词模板 ══════════════════════════════════════════
#
# 【Python】花括号 {} 占位:Python 的 f-string 写法 f"你好,{name}" 会把
# 变量填进字符串。LangChain 的模板借用了同样的语法,只是「先定义、后填值」。
from langchain_core.prompts import ChatPromptTemplate

prompt = ChatPromptTemplate.from_messages([
    ("system", "你是资深的{role},回答要专业但通俗。"),
    ("user", "{question}"),
])

# 模板单独也能用 invoke(还记得吗:万物皆 Runnable,都有 invoke)
# 【Python】{"role": ..., "question": ...} 是「字典」:一组 键→值 的映射,
# 相当于其他语言的 map/object。LangChain 用字典给模板传变量。
filled = prompt.invoke({"role": "营养师", "question": "早餐吃什么好?"})
print("【模板填充后】", filled.messages, "\n")

# ═══ 第 2 步:用 | 串成链 ═══════════════════════════════════════════
#
# 【Python】| 本来是「按位或」运算符。Python 允许类自定义运算符的行为
# (叫「运算符重载」):LangChain 的组件都定义了 __or__ 方法,所以
# a | b 实际执行的是 a.__or__(b),返回一个「把 a 的输出接到 b 的输入」
# 的新组件。这就是 LCEL 管道的全部魔法——没有黑科技,只是语法糖。
from langchain_core.output_parsers import StrOutputParser

chain = prompt | llm | StrOutputParser()
#       模板     模型   把 AIMessage 拆成纯字符串
# 【Python】注意括号!StrOutputParser 是「类」(图纸),StrOutputParser() 才是
# 「实例」(真机器)。链里必须放实例;漏掉括号会报
# TypeError: BaseModel.__init__() takes 1 positional argument but 2 were given

answer = chain.invoke({"role": "营养师", "question": "早餐吃什么好?"})
print("【链的输出】", answer[:120], "...\n")

# 练习2对比:不带解析器的链,输出的是 AIMessage 对象而不是字符串
chain_raw = prompt | llm
raw = chain_raw.invoke({"role": "营养师", "question": "早餐吃什么好?"})
print("【不带解析器】类型 =", type(raw).__name__, "| 要拿文本得写 raw.content\n")
# 整条链也是 Runnable:同样支持 .stream() 和 .batch(),白得的能力!

# ═══ 第 3 步:结构化输出(企业开发必备!) ═══════════════════════════
#
# 场景:你要把模型的回答存数据库、给前端渲染,就不能要一段散文,
# 而要固定格式的数据。让模型「按 schema 返回」就是结构化输出。
#
# 【Python】class 定义一个「类」= 自定义的数据类型。下面继承 Pydantic 的
# BaseModel,每行是「字段名: 类型」的类型标注(str=字符串, int=整数,
# list[str]=字符串列表)。Pydantic 会按这个定义校验数据——类型不对会报错。
# LangChain 则把它翻译成 JSON Schema 发给模型,要求照着填。
from pydantic import BaseModel, Field


class Recipe(BaseModel):
    """一道菜的食谱。"""  # 这行说明文字也会发给模型,写清楚有助于效果

    name: str = Field(description="菜名")
    minutes: int = Field(description="制作耗时(分钟)")
    difficulty: str = Field(description="难度: 简单/中等/困难")
    ingredients: list[str] = Field(description="食材清单")
    calories: int = Field(description="热量")


# with_structured_output 返回一个「输出必为 Recipe 对象」的新模型
structured_llm = llm.with_structured_output(Recipe)

recipe = structured_llm.invoke("推荐一道适合上班族的快手晚餐")
print("【结构化输出】类型 =", type(recipe).__name__)
print("菜名:", recipe.name)
print("耗时:", recipe.minutes, "分钟 | 难度:", recipe.difficulty)
print("食材:", "、".join(recipe.ingredients))
print("热量:", recipe.calories)
# 注意:recipe.name 是能直接用的字段,不用再从文本里正则抠数据!

# ═══ 第 4 步:把模板和结构化输出组合成完整的链 ═══════════════════════
extract_prompt = ChatPromptTemplate.from_messages([
    ("system", "从用户的描述中提取食谱信息。"),
    ("user", "{text}"),
])
extract_chain = extract_prompt | structured_llm

r = extract_chain.invoke({
    "text": "我昨天做了个西红柿炒蛋,番茄两个鸡蛋三个,加点糖和盐,十分钟搞定,零失败"
})
print("\n【从自然语言提取】", r.model_dump())  # model_dump() 把对象转回字典

# ═══════════════════════════════════════════════════════════════
# 练习:
# 1. 给 Recipe 加一个字段 calories: int(热量),看模型能不能估算
# 2. 把 chain 的 StrOutputParser() 去掉再跑,观察输出类型有什么区别
# 3. 用 chain.stream({...}) 流式输出营养师的回答
# ═══════════════════════════════════════════════════════════════
