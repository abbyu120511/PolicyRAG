"""生成两份多页的样例保险条款 PDF,用于测试知识库。

运行: uv run python -m ragapp.make_samples
(-m 表示「以模块方式运行包里的文件」,注意用点不用斜杠、不带 .py)
"""

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

from ragapp.config import DOCS_DIR

# reportlab 默认字体不含中文,注册一个内置的中文字体
pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))

# 数据结构:{文件名: [第1页的行, 第2页的行, ...]}
SAMPLES = {
    "安心重疾险条款.pdf": [
        [
            "安心重疾险 保险条款",
            "第一章 投保须知",
            "本产品投保年龄为出生满 28 天至 60 周岁。",
            "投保人自收到保险合同之日起有 15 天犹豫期,",
            "犹豫期内退保,全额退还已交保险费。",
            "保险期间为终身,交费期可选 10 年、20 年、30 年。",
        ],
        [
            "第二章 保障责任",
            "本合同保障的重大疾病共 100 种。",
            "被保险人经确诊初次发生重大疾病,",
            "本公司按基本保额的 100% 给付重大疾病保险金。",
            "轻症疾病共 40 种,按基本保额的 30% 给付,最多 3 次。",
        ],
        [
            "第三章 等待期与责任免除",
            "本合同的等待期为自生效之日起 90 天。",
            "等待期内确诊重大疾病的,退还已交保费,合同终止。",
            "因投保人对被保险人的故意伤害、被保险人酒后驾驶、",
            "吸食毒品等情形导致的疾病,本公司不承担给付责任。",
        ],
        [
            "第四章 保险金申请",
            "申请重大疾病保险金,应在确诊后 10 日内通知本公司。",
            "需提交:保险合同、被保险人身份证明、",
            "二级以上医院出具的疾病诊断证明书及病理检验报告。",
            "本公司收到齐全材料后 5 个工作日内作出核定;",
            "情形复杂的,在 30 日内作出核定。",
        ],
    ],
    "畅行意外险条款.pdf": [
        [
            "畅行综合意外险 保险条款",
            "第一章 产品概述",
            "本产品保险期间为 1 年,投保年龄 18 至 65 周岁。",
            "意外身故及伤残保险金额为 50 万元。",
            "本产品含意外医疗、住院津贴等附加保障。",
        ],
        [
            "第二章 意外医疗保障",
            "意外医疗费用报销:每次事故免赔额 100 元,",
            "社保范围内费用按 90% 比例报销,",
            "未经社保结算的按 60% 比例报销,年度限额 5 万元。",
            "意外住院津贴为每日 150 元,单次最多 90 天。",
        ],
        [
            "第三章 责任免除",
            "被保险人从事潜水、跳伞、攀岩、探险等高风险运动",
            "期间发生的意外事故,本公司不承担保险责任。",
            "醉酒、无有效驾驶证驾驶机动车造成的事故亦不承担。",
            "war、恐怖袭击、核辐射造成的损失不在保障范围内。",
        ],
    ],
}


def main() -> None:
    for filename, pages in SAMPLES.items():
        path = DOCS_DIR / filename
        c = canvas.Canvas(str(path), pagesize=A4)
        for lines in pages:  # 每个 lines 是一页的内容
            c.setFont("STSong-Light", 14)
            y = 780  # 从页面顶部往下写(PDF 坐标原点在左下角)
            for line in lines:
                c.drawString(72, y, line)
                y -= 28
            c.showPage()  # 结束当前页,开新页
        c.save()
        print(f"生成 {path.name}({len(pages)} 页)")


# 【Python】固定套路:直接运行本文件时 __name__ == "__main__" 为真,main() 执行;
# 被别的文件 import 时不执行。让文件既能当脚本又能当库。
if __name__ == "__main__":
    main()
