from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "materials"
OUT.mkdir(exist_ok=True)
DOCX_PATH = OUT / "01-ADS会议智能体项目说明书.docx"

FONT_CN = "宋体"
FONT_LATIN = "Times New Roman"
BLUE = "1F4E79"
LIGHT_BLUE = "EAF2F8"
PALE_BLUE = "F5F9FC"
GRAY = "5B6573"
BORDER = "C9D7E3"


def set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_border(cell, color: str = BORDER, size: str = "6") -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = tc_pr.first_child_found_in("w:tcBorders")
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = "w:" + edge
        el = borders.find(qn(tag))
        if el is None:
            el = OxmlElement(tag)
            borders.append(el)
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), size)
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), color)


def set_cell_margins(cell, top=60, start=140, bottom=60, end=140) -> None:
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for m, v in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn(f"w:{m}"))
        if node is None:
            node = OxmlElement(f"w:{m}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(v))
        node.set(qn("w:type"), "dxa")


def set_cell_width(cell, width_dxa: int) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_w = tc_pr.find(qn("w:tcW"))
    if tc_w is None:
        tc_w = OxmlElement("w:tcW")
        tc_pr.append(tc_w)
    tc_w.set(qn("w:w"), str(width_dxa))
    tc_w.set(qn("w:type"), "dxa")


def set_table_geometry(table, widths: list[int]) -> None:
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl = table._tbl
    tbl_pr = tbl.tblPr
    tbl_w = tbl_pr.find(qn("w:tblW"))
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(sum(widths)))
    tbl_w.set(qn("w:type"), "dxa")
    tbl_ind = tbl_pr.find(qn("w:tblInd"))
    if tbl_ind is None:
        tbl_ind = OxmlElement("w:tblInd")
        tbl_pr.append(tbl_ind)
    tbl_ind.set(qn("w:w"), "0")
    tbl_ind.set(qn("w:type"), "dxa")
    grid = tbl.tblGrid
    for child in list(grid):
        grid.remove(child)
    for width in widths:
        col = OxmlElement("w:gridCol")
        col.set(qn("w:w"), str(width))
        grid.append(col)
    for row in table.rows:
        for i, cell in enumerate(row.cells):
            set_cell_width(cell, widths[i])
            set_cell_margins(cell)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            set_cell_border(cell)


def set_run_font(run, font_name: str, size: float = 12, bold: bool | None = None, color: str | None = None, italic: bool | None = None):
    run.font.name = font_name
    run.font.size = Pt(size)
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.rFonts
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:ascii"), font_name)
    rfonts.set(qn("w:hAnsi"), font_name)
    rfonts.set(qn("w:eastAsia"), font_name)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    if color:
        run.font.color.rgb = RGBColor.from_string(color)


def add_mixed(paragraph, text: str, size: float = 12, bold: bool = False, color: str | None = None, italic: bool = False):
    parts = re.split(r"([A-Za-z0-9]+)", text)
    for part in parts:
        if not part:
            continue
        family = FONT_LATIN if re.fullmatch(r"[A-Za-z0-9]+", part) else FONT_CN
        run = paragraph.add_run(part)
        set_run_font(run, family, size=size, bold=bold, color=color, italic=italic)


def format_para(p, *, first_indent: bool = True, before=0, after=0, line=22, align=WD_ALIGN_PARAGRAPH.LEFT):
    pf = p.paragraph_format
    pf.alignment = align
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    pf.line_spacing = Pt(line)
    pf.first_line_indent = Pt(24) if first_indent else Pt(0)


def add_body(doc, text: str, *, first_indent=True, after=0, color="222222", bold=False):
    p = doc.add_paragraph()
    format_para(p, first_indent=first_indent, after=after)
    add_mixed(p, text, size=12, bold=bold, color=color)
    return p


def add_heading(doc, text: str, level=1):
    p = doc.add_paragraph()
    format_para(p, first_indent=False, before=10 if level == 1 else 6, after=4, line=22)
    add_mixed(p, text, size=16 if level == 1 else 14, bold=True, color=BLUE)
    return p


def add_label_paragraph(doc, label: str, text: str):
    p = doc.add_paragraph()
    format_para(p, first_indent=False, after=2)
    add_mixed(p, label, size=12, bold=True, color=BLUE)
    add_mixed(p, text, size=12, color="222222")
    return p


def add_table(doc, headers: list[str], rows: list[list[str]], widths: list[int]):
    table = doc.add_table(rows=1, cols=len(headers))
    set_table_geometry(table, widths)
    for i, header in enumerate(headers):
        cell = table.rows[0].cells[i]
        set_cell_shading(cell, LIGHT_BLUE)
        p = cell.paragraphs[0]
        format_para(p, first_indent=False, line=22, align=WD_ALIGN_PARAGRAPH.CENTER)
        add_mixed(p, header, size=12, bold=True, color=BLUE)
    for ridx, row in enumerate(rows):
        cells = table.add_row().cells
        for i, value in enumerate(row):
            if ridx % 2 == 1:
                set_cell_shading(cells[i], PALE_BLUE)
            p = cells[i].paragraphs[0]
            format_para(p, first_indent=False, line=22)
            add_mixed(p, value, size=12, color="222222")
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return table


def add_callout(doc, label: str, text: str):
    table = doc.add_table(rows=1, cols=1)
    set_table_geometry(table, [9070])
    cell = table.cell(0, 0)
    set_cell_shading(cell, "F0F6FA")
    p = cell.paragraphs[0]
    format_para(p, first_indent=False, after=0, line=22)
    add_mixed(p, label + "：", size=12, bold=True, color=BLUE)
    add_mixed(p, text, size=12, color="25313D")
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def add_page_number(paragraph):
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = paragraph.add_run("第 ")
    set_run_font(run, FONT_CN, size=9, color=GRAY)
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), "PAGE")
    paragraph._p.append(fld)
    run2 = paragraph.add_run(" 页")
    set_run_font(run2, FONT_CN, size=9, color=GRAY)


def setup_doc(doc: Document):
    sec = doc.sections[0]
    sec.page_width = Cm(21)
    sec.page_height = Cm(29.7)
    sec.top_margin = Cm(2.2)
    sec.bottom_margin = Cm(2.0)
    sec.left_margin = Cm(2.5)
    sec.right_margin = Cm(2.5)
    sec.header_distance = Cm(1.0)
    sec.footer_distance = Cm(1.0)

    normal = doc.styles["Normal"]
    normal.font.name = FONT_CN
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CN)
    normal._element.rPr.rFonts.set(qn("w:ascii"), FONT_LATIN)
    normal._element.rPr.rFonts.set(qn("w:hAnsi"), FONT_LATIN)
    normal.font.size = Pt(12)
    normal.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    normal.paragraph_format.line_spacing = Pt(22)
    normal.paragraph_format.first_line_indent = Pt(24)

    header = sec.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.LEFT
    header.paragraph_format.space_after = Pt(0)
    header.paragraph_format.line_spacing = Pt(12)
    add_mixed(header, "ADS 会议智能体｜项目说明书", size=9, color=GRAY)
    footer = sec.footer.paragraphs[0]
    add_mixed(footer, "项目材料 · 2026年8月", size=9, color=GRAY)
    add_page_number(footer)


def build():
    doc = Document()
    setup_doc(doc)

    # Cover / masthead
    p = doc.add_paragraph()
    format_para(p, first_indent=False, before=20, after=2, line=26, align=WD_ALIGN_PARAGRAPH.CENTER)
    add_mixed(p, "项目说明书", size=22, bold=True, color=BLUE)
    p = doc.add_paragraph()
    format_para(p, first_indent=False, after=12, line=26, align=WD_ALIGN_PARAGRAPH.CENTER)
    add_mixed(p, "ADS 会议智能体：会前聚合、AI 代理参会与会后闭环系统", size=16, bold=True, color="263746")
    p = doc.add_paragraph()
    format_para(p, first_indent=False, after=18, line=22, align=WD_ALIGN_PARAGRAPH.CENTER)
    add_mixed(p, "面向项目负责人和团队成员的本地会议协作产品", size=12, color=GRAY)

    add_table(doc, ["项目属性", "内容"], [
        ["项目定位", "PC 端本地运行的会议协作与任务闭环工具"],
        ["核心对象", "ADS 工作区、会议、决策、行动项与来源审计"],
        ["核心流程", "会前聚合 → 会中协作/代理参会 → 会后任务写回"],
        ["当前版本", "原型开发阶段，已完成核心流程的源码实现与专项验证"],
        ["材料用途", "项目成果说明、功能价值与技术方案概览"],
    ], [2100, 6970])
    add_callout(doc, "核心价值", "用户不必在每场会议中重复同步背景信息。智能体在明确授权范围内读取 ADS 业务上下文、整理会议内容，只把真正需要新判断的事项交给本人，并将确认后的结果转化为可跟踪的 ADS 任务。")

    p = doc.add_paragraph()
    format_para(p, first_indent=False, before=12, after=0, line=22, align=WD_ALIGN_PARAGRAPH.CENTER)
    add_mixed(p, "启智杯 AI 应用成果挑战赛 · 原型开发材料", size=10, color=GRAY)
    doc.add_page_break()

    add_heading(doc, "一、项目概述", 1)
    add_body(doc, "ADS 会议智能体是一套面向项目负责人、部门负责人及团队成员的 PC 端会议协作产品。产品以 ADS 工作区为业务事实基础，将团队成员、项目、目标、指标、风险、制度、任务、历史立场和授权边界，形成会议可直接使用的上下文。")
    add_body(doc, "围绕一场会议，系统先完成会前资料聚合和简报生成，再在会议现场接收文字或音频内容，持续识别决策、风险和行动项；当事项超出授权范围时，系统将其升级给本人确认。会议结束后，用户可以检查有效纪要、补全行动项并写回 ADS，最后在审计页面追溯原始输入、判断依据和任务来源。")
    add_body(doc, "本项目的差异化不在于单纯把语音转换成文字，而在于将会议中的业务判断与后续执行连接起来：会议内容必须关联 ADS 对象，智能体必须说明事实和授权依据，行动项必须经过本人确认后才能成为可跟踪任务。")

    add_heading(doc, "二、现实问题与建设目标", 1)
    add_table(doc, ["现实问题", "产品目标"], [
        ["项目资料分散在人员、任务、风险和制度等多个位置，参会者需要重复同步背景。", "以 ADS 工作区为统一上下文，自动汇总与当前会议相关的业务资料，生成会前简报和建议议程。"],
        ["会议中普通进度和高风险决策混在一起，智能化工具容易越权代替本人判断。", "建立授权内处理与超权升级机制，对新增预算、改变技术路线等事项明确交给本人决定。"],
        ["会议结束后，摘要和行动项常常停留在文字中，缺少负责人、日期和执行状态。", "将决策和行动项结构化，支持负责人、截止日期确认和独立写回 ADS 任务。"],
        ["旧提案、修改意见和最终结论容易混在同一份纪要中，难以核对过程。", "只展示当前有效成果，同时保留原始输入、本人回复和处理时间，形成可追溯审计链。"],
    ], [3500, 5570])

    add_heading(doc, "三、总体解决方案", 1)
    add_body(doc, "产品采用“ADS 业务上下文 + 会议工作空间 + 决策中心 + 会后写回”的组合结构。用户先在 ADS 工作区建立业务对象，再创建会议并选择关联工作区；系统根据会议目标和关联对象生成会前准备内容，会议中按授权规则处理发言，会议后将经过本人确认的行动项写回 ADS。")
    add_table(doc, ["阶段", "主要处理", "输出"], [
        ["会前聚合", "检索项目、目标、指标、风险、任务、制度和历史立场；生成简报和议程建议。", "会前简报、待确认问题、授权建议"],
        ["会中协作", "接收文字、浏览器录音或音频文件；识别事实、共识、争议、风险和行动项。", "转写记录、分析结果、建议回复"],
        ["授权判断", "区分授权内事项与必须本人确认的事项；将超权事项集中到决策中心。", "授权依据、升级事项、本人决定"],
        ["会后闭环", "重建当前有效纪要，补全行动项负责人和截止日期，逐项写回 ADS。", "有效纪要、ADS 任务、写回状态"],
        ["过程审计", "关联原始发言、转写片段、模型调用、授权判断、本人操作和写回结果。", "来源链、事件时间线、可下钻对象"],
    ], [1800, 4470, 2800])

    add_heading(doc, "四、核心功能模块", 1)
    add_table(doc, ["模块", "功能说明", "当前状态"], [
        ["ADS 工作区", "管理成员、项目、目标、指标、风险、任务、制度、历史立场和授权规则。", "已实现并完成工作区对象关联验证"],
        ["会议管理", "创建会议、关联 ADS 上下文、选择参与方式和当前会议，提供明确的开始、结束和重新打开操作。", "已实现并完成生命周期专项验证"],
        ["会前准备", "生成会前简报、建议议程、待确认问题和本场授权建议。", "已实现，随会议创建流程使用"],
        ["会议现场", "提交文字、录音或音频，持续分析发言并形成会议过程记录。", "文字流程已验证，本地语音能力按环境检查"],
        ["智能体代理", "在本人授权范围内提供建议或代理回复，超权事项升级给本人。", "核心流程已实现，在线模型真实密钥验收仍需单独进行"],
        ["决策中心", "跨会议汇总待本人事项，支持同意、修改后回复、拒绝和暂不处理。", "已实现并完成修改/拒绝结果验证"],
        ["会议成果", "展示当前有效纪要、决策、行动项、负责人、截止日期和依据。", "已实现有效纪要重建"],
        ["ADS 写回", "支持行动项逐条写回、失败保留和重试，写回不代替用户结束会议。", "已实现并完成写回分离验证"],
        ["审计与来源", "保留原始提案、本人回复、有效决定和 ADS 任务之间的来源关系。", "已实现并完成隔离浏览器验证"],
        ["数据看板", "按工作区和日期范围展示会议过程指标、指标口径和人工基准入口。", "已实现；真实自定义日期交互仍需补充验证"],
    ], [1900, 4970, 2200])

    doc.add_page_break()
    add_heading(doc, "五、产品使用流程", 1)
    add_table(doc, ["步骤", "用户操作", "系统反馈"], [
        ["1. 建立上下文", "创建或选择 ADS 工作区，维护成员、项目、目标、风险、任务和授权规则。", "形成可供会议检索的业务事实。"],
        ["2. 创建会议", "填写时间、参会人、会议目标和议程，关联工作区。", "生成会前简报和建议议程。"],
        ["3. 明确当前会议", "在顶部选择当前会议，进入现场并点击“开始会议”。", "避免输入误投，会议进入进行中状态。"],
        ["4. 处理发言", "输入普通进度或涉及技术路线、预算的发言。", "授权内内容形成行动项，超权内容进入决策中心。"],
        ["5. 本人决策", "同意、修改、拒绝或暂不处理升级事项。", "决定返回原会议，旧提案按规则保留或移出当前成果。"],
        ["6. 整理写回", "结束会议，检查有效纪要，补全负责人和截止日期并写回。", "生成 ADS 任务，会议进程和成果状态分别保留。"],
        ["7. 追溯复核", "查看审计与来源页面。", "回放原始发言、判断、本人回复和写回链路。"],
    ], [1250, 4450, 3370])

    add_heading(doc, "六、技术实现", 1)
    add_body(doc, "前端采用 React 19、TypeScript 和 Vite，负责工作台、会议空间、决策中心、ADS 工作区、设置和数据看板等交互页面。前端通过统一的接口层访问会议、模型、语音、ADS 和写回服务，并在关键状态上提供明确的加载、成功、失败和空状态反馈。")
    add_body(doc, "后端采用 Python FastAPI，负责会议生命周期、ADS 上下文、统一分析流程、授权判断、行动项写回、模型调用审计和语音任务管理。SQLite 用于保存会议、工作区、任务、模型配置、转写任务和审计元数据；原始音频与运行资源保存在受控本地目录。")
    add_body(doc, "模型层通过统一 Provider 接口支持在线模型和本地规则模式。当前源码包含 DeepSeek 等在线模型配置入口，并保留本地规则降级路径；本地语音处理使用 FFmpeg 和 faster-whisper-small，语音能力是否可用以启动后的健康检查结果为准。")
    add_table(doc, ["技术层", "采用方案", "作用"], [
        ["交互层", "React 19 + TypeScript + Vite", "提供 PC 端会议工作台、ADS 工作区和结果处理界面"],
        ["服务层", "Python FastAPI", "提供会议、分析、授权、写回、审计和语音任务 API"],
        ["数据层", "SQLite + 本地文件目录", "保存业务对象、会议状态、任务状态、转写元数据和审计记录"],
        ["模型层", "统一 ModelProvider + 本地规则降级", "支持会议分析、问答、回复建议和结构化结果生成"],
        ["语音层", "FFmpeg + faster-whisper-small", "完成音频预处理和本地中文转写；按环境检查结果启用"],
    ], [1800, 3300, 3970])

    add_heading(doc, "七、产品特色与应用价值", 1)
    add_label_paragraph(doc, "1. 业务上下文接地。", "会议不是独立的聊天窗口，而是与人员、项目、目标、风险、制度和历史立场建立关系，减少重复同步和脱离业务事实的回答。")
    add_label_paragraph(doc, "2. 授权边界清晰。", "系统将“可以直接整理的事项”和“必须由本人做新判断的事项”分开处理，既提高效率，也避免智能体越权。")
    add_label_paragraph(doc, "3. 会议结果可执行。", "结构化纪要、负责人、截止日期和 ADS 写回让会议结论从文字记录转化为可跟踪任务。")
    add_label_paragraph(doc, "4. 修改过程可追溯。", "当前成果只保留有效决定，原始提案和本人回复仍在审计中保留，兼顾结果清晰与过程可核验。")
    add_label_paragraph(doc, "5. 本地优先。", "产品可以在单台 Windows PC 上运行，支持本地规则和本地语音资源；在线模型为可配置能力，密钥保存在本机后端。")
    add_callout(doc, "适用场景", "项目周会、技术评审会、交付协调会和跨部门协同会。尤其适用于需要同时处理多场会议、频繁做授权判断、并要求会后任务落地的项目负责人。")

    add_heading(doc, "八、当前实现状态与交付边界", 1)
    add_table(doc, ["状态", "本项目中的含义"], [
        ["已实现", "源码已具备对应功能，页面、接口和数据结构能够完成相应操作。"],
        ["已验证", "已有自动化测试或隔离浏览器流程证据支持，不以“按钮存在”代替验收。"],
        ["未验证", "代码可能已经具备，但还没有在目标环境、真实密钥或完整场景中完成最终验收。"],
        ["当前边界", "本版本定位为单机 PC 原型/首个稳定产品版，不包含多租户、局域网多人编辑和正式外部会议平台接入。"],
    ], [2200, 6870])
    add_body(doc, "截至本材料编写时，会议生命周期、当前会议选择、有效纪要重建和数据看板范围等近期体验改进已完成源码实现及专项回归；在线模型真实密钥、双分辨率完整验收、部分语音环境和 Windows 最新发行包仍应在对应环境中单独确认。")
    add_body(doc, "项目不以固定演示剧本或预置结果替代真实流程。演示使用的“演示-”前缀业务数据仅用于说明产品操作路径，正式业务使用时应替换为用户自己的 ADS 工作区内容。")

    add_heading(doc, "九、结语", 1)
    add_body(doc, "ADS 会议智能体将会议理解、授权判断和任务执行放在同一个闭环中：会前把业务事实带入会议，会中把真正需要本人判断的事项交给本人，会后把确认后的结果写回 ADS 并保留完整来源。产品的目标不是让智能体替用户做所有决定，而是在清晰边界内减少重复劳动，让每一个重要决定都能被看见、被确认、被执行和被追溯。")

    doc.core_properties.title = "ADS会议智能体项目说明书"
    doc.core_properties.subject = "项目成果与产品方案说明"
    doc.core_properties.author = "ADS会议智能体项目组"
    doc.core_properties.comments = ""
    doc.save(DOCX_PATH)
    print(DOCX_PATH)


if __name__ == "__main__":
    build()
