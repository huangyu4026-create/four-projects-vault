from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

try:
    from formal_honglou_eight_step_mainline import build_eight_step_packet
except Exception:  # pragma: no cover - import fallback for isolated reads
    build_eight_step_packet = None  # type: ignore[assignment]

try:
    from formal_honglou_library_tier_selector import select_libraries
except Exception:  # pragma: no cover - import fallback for isolated reads
    select_libraries = None  # type: ignore[assignment]

try:
    from formal_honglou_aggregation_graph_runtime import build_aggregation_graph_packet
except Exception:  # pragma: no cover - import fallback for isolated reads
    build_aggregation_graph_packet = None  # type: ignore[assignment]

try:
    from formal_honglou_two_layer_checkin_gate import build_two_layer_checkin_packet
except Exception:  # pragma: no cover - import fallback for isolated reads
    build_two_layer_checkin_packet = None  # type: ignore[assignment]

try:
    import formal_honglou_question_decomposer as decomposer
except Exception:  # pragma: no cover - route_context is optional for isolated reads
    decomposer = None  # type: ignore[assignment]


RUNTIME_BUS_NAME = "红楼梦工程运行总线"
SHARED_EIGHT_STEP_SPINE = [
    "归一",
    "收点",
    "交集",
    "路由门",
    "分类",
    "回原文",
    "入材料池",
    "写答案",
]
SHARED_EIGHT_STEP_FORMULA = " -> ".join(SHARED_EIGHT_STEP_SPINE)
QUERY_HEADS = {
    "进入聚拢查询": {
        "lane": "semantic_aggregation",
        "tooling": "语义聚拢中心库 / 聚拢总图 / 中心库表轴",
        "shared_spine": SHARED_EIGHT_STEP_FORMULA,
    },
    "进入坐标查询": {
        "lane": "coordinate",
        "tooling": "坐标查询中心库 / 全文词位库 / 字位桥表 / 变量投影库",
        "shared_spine": SHARED_EIGHT_STEP_FORMULA,
    },
}
RUNTIME_MAIN_FLOW = [
    "用户问题",
    "接入红楼梦工程入口",
    "创建或确认本题闭环包 package_dir",
    "自检 00AC/00AG/00AI/00AM 聚拢四件套",
    "四件套齐全后进入聚拢库 / 聚拢总图",
    "外部判题打卡",
    "聚拢总图加载",
    "聚拢总图读法加载",
    "入口词与入图盘面打卡",
    "姓名/别名/对象/空间/时间归一",
    "来源规则熔入唯一新流程验收",
    "归一/中心库表轴/拆题/穷尽/入池/复核规则全集加载",
    "现成新编号入口门收点",
    "必要时全文穷尽补点",
    "问题树 / 问题单元",
    "子问题内两两比较 / 两组对照方法",
    "图内放大缩小与交集路由",
    "子问题材料池归类",
    "Codex 材料池判定",
    "子问题出卷闸门",
    "必要补证循环",
    "聚拢裁判通过后才写最终答案",
    "终稿后质量复核",
]


def new_flow_required_rule_set() -> list[dict[str, str]]:
    return [
        {
            "rule_id": "R01_package_and_four_piece_gate",
            "source_basis": "000/127/131 根门与双打卡",
            "source_files": "000_进入红楼梦工程_新窗口强制入口.md；127_进入红楼梦工程打卡门_必读已加载清单.md；131_红楼梦工程唯一运行顺序与双打卡验收基线.md",
            "required_rule": "确认进入红楼梦工程，禁止自由搜索，要求 package_dir 与 00AC/00AG/00AI/00AM。",
            "flow_slot": "唯一入口第 2-4 步：接入口 -> 闭环包 -> 聚拢四件套自检。",
            "enforcement": "首道硬入口；缺本题闭环包或四件套不算进入聚拢库。",
            "acceptance_evidence": "00AC 首句、00AG、00AI、00AM 与 package_dir 同时存在并已读。",
            "old_execution_permission": "0；来源文件只作规则依据，不作另一路径。",
            "block_rule": "无 package_dir 或四件套缺失，不得进入正文答案。",
        },
        {
            "rule_id": "R02_library_map_and_registry",
            "source_basis": "18/20/21/25/128 库地图与库登记处",
            "source_files": "18_库群一屏说明与使用指南.md；20_库登记处查法与专题库补漏表.md；21_AI入场后全库利用与流转总指导.md；25_库登记处机器总表.csv；128_聚拢库总入口_全库地图与流程记录.md",
            "required_rule": "说明语义聚拢中心库、中心库内部表轴、防漏路径和每类表轴的证据角色。",
            "flow_slot": "聚拢四件套之后、库检索之前：直达语义聚拢中心库，再决定中心库内部表轴。",
            "enforcement": "作为中心库结构加载和防漏门；语义路线不得另选外部库作为候选来源。",
            "acceptance_evidence": "00AC 记录语义聚拢中心库已加载，并列出内部表轴与证据角色。",
            "old_execution_permission": "0；库登记处不作前门，只作中心库内部表轴说明与防漏依据。",
            "block_rule": "无语义聚拢中心库/内部表轴记录，不能说唯一新流程规则全集已加载。",
        },
        {
            "rule_id": "R03_entry_terms_and_normalization",
            "source_basis": "126/127/117 查询词入口规范",
            "source_files": "126_聚龙法查询词入口规范_单字宽网.md；127_进入红楼梦工程打卡门_必读已加载清单.md；117_聚拢总图新入口SOP与触发词同步包.md",
            "required_rule": "人物先归一；物象、小词、动作、文本功能走最小根字、疑义宽网和绑定词。",
            "flow_slot": "入口词与入图盘面打卡之前：先做姓名/对象/空间/时间归一与词根规范。",
            "enforcement": "必经闸门；入口词不清楚只允许补卡，不准自由搜索。",
            "acceptance_evidence": "入图盘面记录题面词、归一人物、根字、绑定词和补卡状态。",
            "old_execution_permission": "0；查询词规则只作生成入口词的标准，不作检索前门。",
            "block_rule": "无入口词、无归一、无入图盘面，不得启动库检索。",
        },
        {
            "rule_id": "R04_person_alias_identity",
            "source_basis": "70/72/18 人物姓名、别名、称谓归一",
            "source_files": "70_全人物别名归一总表.csv；72_人物查询归一包_全量生成表.json；18_库群一屏说明与使用指南.md",
            "required_rule": "把人物、别名、称谓、异写归到可查身份，并保留语境差异。",
            "flow_slot": "进入聚拢总图前的对象归一层，以及人物题/关系题的第一动作。",
            "enforcement": "前置执行；新入口不得替代人物归一。",
            "acceptance_evidence": "问题包记录 canonical_person、aliases_used、person_ids 或缺口说明。",
            "old_execution_permission": "0；别名表只作归一依据，不开启旧人物查询前门。",
            "block_rule": "人物未归一，多轴共现和关系题不得入材料池。",
        },
        {
            "rule_id": "R05_formal_library_priority_inside_graph",
            "source_basis": "63 正式库优先与问题单元",
            "source_files": "63_红楼梦工程AI入口SOP_正式库优先版.md",
            "required_rule": "正式库优先，但正式库材料必须分配到具体子问题，不能吞掉总答案。",
            "flow_slot": "语义聚拢中心库入口之后的中心表轴深读层。",
            "enforcement": "保留正式库优先的资料价值，但取消其前门地位；正式库信息必须映射回中心库、回原文、入材料池。",
            "acceptance_evidence": "每条正式库材料有 subquestion_refs、source_role、return_to_original_status。",
            "old_execution_permission": "0；正式库不是前门，只能在聚拢库内作为优先资料源。",
            "block_rule": "正式库命中未归属到问题单元或未回原文，不得升格为主证。",
        },
        {
            "rule_id": "R06_problem_tree_and_subquestion_eight_steps",
            "source_basis": "51/63/87/88/90 复杂题、问题树、子问题八步",
            "source_files": "51_红楼梦工程AI入场SOP.md；63_红楼梦工程AI入口SOP_正式库优先版.md；87_红楼梦编号证据八步主线_总规则.md；88_SOP同步包_子问题八步与补证循环.md；90_运行总线程序化落地.md",
            "required_rule": "复杂题先进入完整八步法；八步法内部先做取词之前的思考，再做取词以后如何用库的思考，并逐子问题查库、入池、覆盖判定和出卷闸门。",
            "flow_slot": "问题类型判定之后、中心库表轴取材和材料池之前。",
            "enforcement": "显式深度题、复杂题、多论证题必须按八步法形成入口词包，并按八步法逐子问题过账。",
            "acceptance_evidence": "01_问题树、子问题材料池归类、coverage_status、出卷闸门同时存在。",
            "old_execution_permission": "0；八步不作库外并行主路，只作为聚拢库内的子问题复核步骤。",
            "block_rule": "复杂题无问题树、无子问题覆盖状态，不得出卷。",
        },
        {
            "rule_id": "R07_comparison_inside_problem_unit",
            "source_basis": "比较对照线 / 两两比较经验",
            "source_files": "formal_honglou_closed_loop.py: question_query_experience_skeleton；51/63 的问题单元规则",
            "required_rule": "比较题要有对象A、对象B、共同维度、同场对照和反证边界。",
            "flow_slot": "问题单元或子问题内部的方法层。",
            "enforcement": "作为方法保留；先判断是否需要问题树，再在相应问题单元内比较。",
            "acceptance_evidence": "比较题记录对象A/B、共同维度、证据强弱、反证边界。",
            "old_execution_permission": "0；比较方法无前门路权，不触发任何旁路。",
            "block_rule": "已进入比较/对照的问题单元无共同维度和反证边界，不得出卷。",
        },
        {
            "rule_id": "R08_numbering_collection_inside_graph",
            "source_basis": "新编号入口门",
            "source_files": "74_旧前门封城与新编号入口唯一前门总规则.json；120_聚拢总图中段替换与旧工具吸纳硬规则.md；131_红楼梦工程唯一运行顺序与双打卡验收基线.md",
            "required_rule": "保留编号收点能力。",
            "flow_slot": "聚拢总图内部收点工具。",
            "enforcement": "作为图内工具；产出的编号必须回聚拢层级与原文。",
            "acceptance_evidence": "候选记录编号、聚拢段/单元/事件/场/域和原文出口。",
            "old_execution_permission": "0；编号入口门无前门路权，只能在 00AC 后图内调用。",
            "block_rule": "编号未回聚拢总图和原文裁判，只能算候选。",
        },
        {
            "rule_id": "R09_exhaustive_sweep_inside_graph",
            "source_basis": "全书穷尽查证 / 语义聚拢中心库内部全文表轴 / FTS",
            "source_files": "20_库登记处查法与专题库补漏表.md；21_AI入场后全库利用与流转总指导.md；63_红楼梦工程AI入口SOP_正式库优先版.md；120_聚拢总图中段替换与旧工具吸纳硬规则.md；131_红楼梦工程唯一运行顺序与双打卡验收基线.md",
            "required_rule": "详查、全查、小物象、小动作、漏库时的全文补证工具。",
            "flow_slot": "语义聚拢中心库无命中、候选过窄或中心表轴可能漏收时的补点层。",
            "enforcement": "关闭为前门；补出来的 segment_no/编号必须回语义聚拢中心库、聚拢图和原文。",
            "acceptance_evidence": "穷尽词、命中范围、误召回剔除、回图编号和原文裁判记录齐全。",
            "old_execution_permission": "0；FTS/SQLite 不可起手，只可在聚拢库内补漏。",
            "block_rule": "全查/详查/有没有/多对象同场题无穷尽记录，不得最终定论。",
        },
        {
            "rule_id": "R10_multi_axis_scene_convergence",
            "source_basis": "109/102/105 多库线索向场会合与现场裁决",
            "source_files": "109_多库线索向场会合_全库设计总规则.md；102_红楼梦现场裁决九步法_总规则.md；105_证据颗粒上升到场_策略优化总规则.md",
            "required_rule": "人物、物象、空间、时间、事件等多库线索必须会合到场、段、事件和原文现场。",
            "flow_slot": "聚拢总图内放大/缩小/交集/串域和多轴共现路由。",
            "enforcement": "作为聚拢库内部裁判动作；多轴题默认要会合到现场。",
            "acceptance_evidence": "轴项归一、共同段/场/事件、动作链、原文现场和证据角色齐全。",
            "old_execution_permission": "0；多库规则只作聚拢库内裁判法，不开多库并行前门。",
            "block_rule": "多轴线索未会合到聚拢场或原文现场，不得入主证。",
        },
        {
            "rule_id": "R11_graph_reading_and_material_four_states",
            "source_basis": "117/119/128/131 聚拢总图读法与材料池四态",
            "source_files": "117_聚拢总图新入口SOP与触发词同步包.md；119_聚拢总图图内读法与问题思维方式.md；128_聚拢库总入口_全库地图与流程记录.md；131_红楼梦工程唯一运行顺序与双打卡验收基线.md",
            "required_rule": "节点、标签、线索、候选、原文裁判、材料池四态的判读规则。",
            "flow_slot": "新入口的唯一中段和出口裁判层。",
            "enforcement": "唯一中段；标签/命中不能当答案。",
            "acceptance_evidence": "材料池四态、聚拢裁判、原文裁判与不可用/需补证记录齐全。",
            "old_execution_permission": "0；这是新流程自身的唯一中段，不允许其他中段并行。",
            "block_rule": "无聚拢裁判、无材料池四态，不写最终红楼解语。",
        },
        {
            "rule_id": "R12_material_admission_certificate",
            "source_basis": "76 材料池入池凭证门",
            "source_files": "76_材料池入池凭证门_程序化落地.md",
            "required_rule": "阻止无编号、无来源、无子问题归属的材料入池。",
            "flow_slot": "原文裁判之后、Codex 精读之前。",
            "enforcement": "硬闸；新增聚拢节点、聚拢段、聚拢单元、聚拢事件等凭证字段。",
            "acceptance_evidence": "入池清单含 source_layer、segment_no、aggregation_node、subquestion_refs、evidence_role。",
            "old_execution_permission": "0；材料池门保留为新流程硬闸，不开启旧材料池旁路。",
            "block_rule": "无入池凭证，不得把候选升格为主证。",
        },
        {
            "rule_id": "R13_prewrite_original_trace_and_final_review",
            "source_basis": "00I / 00L / 00M / 写作前原文追证 / 终稿后质量复核",
            "source_files": "90_运行总线程序化落地.md；120_聚拢总图中段替换与旧工具吸纳硬规则.md；131_红楼梦工程唯一运行顺序与双打卡验收基线.md",
            "required_rule": "材料池后先做 00I 材料池判定，再做 00L 精读材料词，再做 00M 写作前原文摘抄，最终答案后复核质量。",
            "flow_slot": "材料池四态之后、最终答案之前和终稿之后。",
            "enforcement": "接在聚拢裁判之后；00I/00L/00M 是最终答案硬前置，最终答案前后均需过门。",
            "acceptance_evidence": "00I_Codex材料池判定、00L_Codex精读材料词、00M_Codex写作前原文摘抄、最终答案门、终稿复核记录齐全。",
            "old_execution_permission": "0；复核工具只作出口硬闸，不回到旧写作路径。",
            "block_rule": "00I/00L/00M 任一缺失，不写最终红楼解语。",
        },
        {
            "rule_id": "R14_seal_old_shortcuts",
            "source_basis": "旧候选提示卡 / 旧搜索词网络 / 旧库分级选库 / 快速落盘",
            "source_files": "115_旧方案封锁封板与运行前门切换方案.md；116_旧前门硬封锁执行令_机器拦截规则.json；120_聚拢总图中段替换与旧工具吸纳硬规则.md",
            "required_rule": "只保留候选建议、补漏经验和封锁证据。",
            "flow_slot": "只能作为后台参考、候选建议或补漏工具。",
            "enforcement": "前门关闭；有用能力保留，路径权力清零。",
            "acceptance_evidence": "00AC 显性写明 sealed_as_front_door / 召回已命中，待聚拢裁判。",
            "old_execution_permission": "0。",
            "block_rule": "任何可直接命中只能记为召回已命中，待聚拢裁判；不得跳过 00I/00L/00M。",
        },
        {
            "rule_id": "R15_maintenance_not_answer_route",
            "source_basis": "锚点修复、映射审计、简繁异体、维护工具",
            "source_files": "120_聚拢总图中段替换与旧工具吸纳硬规则.md；40_W05_W06_锚点债与穷尽查证审计报告.md；各映射审计/锚点修复文件",
            "required_rule": "修底座、补断链、处理异体和映射健康。",
            "flow_slot": "聚拢总图断链、原文锚点缺失、检索漏召回时的维护层。",
            "enforcement": "维护职务，不并入答题前门。",
            "acceptance_evidence": "断链、锚点缺失、简繁漏召回被标为维护任务或补证任务。",
            "old_execution_permission": "0；维护工具无答题路权。",
            "block_rule": "断链未修复或未标缺口，相关材料不得升格为强证。",
        },
    ]

EXPLICIT_DECOMPOSE_TRIGGERS = [
    "拆成子问题",
    "展开问题分析思路",
    "先出子问题",
    "分层分析",
    "逐项回答",
    "分步骤出卷",
    "分几个问题",
]

COMPARISON_METHOD_TERMS = [
    "两两比较",
    "两组",
    "比较",
    "对照",
    "差异",
    "异同",
    "相同",
    "不同",
    "高下",
    "一组",
    "另一组",
]

DEEP_RESEARCH_TRIGGERS = [
    "进入深度研究",
    "进入复杂思考",
    "进入全量输出",
    "进入深度逻辑推理",
    "深度研究",
    "复杂思考",
    "全量输出",
    "深度逻辑推理",
    "展开深度分析",
    "完整论证",
]

FAST_FACT_TRIGGERS = [
    "第几回",
    "章回",
    "姓什么",
    "叫什么",
    "是哪一回",
    "是谁",
]


@dataclass(frozen=True)
class RuntimeDecision:
    question: str
    should_decompose: bool
    decompose_reason: str
    fast_path_allowed: bool
    required_gates: list[str]
    deep_mode_requested: bool
    comparison_method_requested: bool
    argument_unit_count: int
    argument_units: list[str]


def _contains_any(text: str, needles: list[str]) -> bool:
    return any(needle in text for needle in needles)


def extract_argument_units(question: str) -> list[str]:
    """Split a user question into visible argument units, not keyword triggers."""
    normalized = " ".join(str(question or "").split())
    if not normalized:
        return []
    parts = re.split(
        r"[？?。；;]+|(?:^|[，,、\s])(同时|另外|还有|并且|以及|其次|再次|最后|一是|二是|三是)(?:[，,、\s]|$)",
        normalized,
    )
    units: list[str] = []
    for part in parts:
        value = str(part or "").strip(" ，,、：:。；;？?")
        if len(value) < 4:
            continue
        if value not in units:
            units.append(value)
    return units


def decide_runtime_route(question: str) -> RuntimeDecision:
    explicit = _contains_any(question, EXPLICIT_DECOMPOSE_TRIGGERS)
    deep_mode = _contains_any(question, DEEP_RESEARCH_TRIGGERS)
    comparison_method = _contains_any(question, COMPARISON_METHOD_TERMS)
    argument_units = extract_argument_units(question)
    argument_unit_count = len(argument_units)
    multi_argument = argument_unit_count > 2
    # Old fast-answer routing is closed. Keep the trigger list only as audit vocabulary;
    # even fact-like questions must pass package_dir and 00AC/00AG/00AI/00AM.
    fast_fact = False

    if explicit:
        should_decompose = True
        reason = "用户显式要求拆成子问题或展开问题分析。"
    elif deep_mode:
        should_decompose = True
        reason = "用户显式触发深度研究或复杂思考。"
    elif multi_argument:
        should_decompose = True
        reason = f"题内有 {argument_unit_count} 个论证单元，超过两个，需要先拆成子问题。"
    else:
        should_decompose = False
        reason = f"题内论证单元 {argument_unit_count} 个，未触发深度要求；按原问题单元执行。"

    required_gates = [
        "本题闭环包凭证",
        "聚拢四件套自检",
        "外部判题打卡",
        "入口词与入图盘面打卡",
        "聚拢总图加载",
        "聚拢总图读法加载",
        "唯一新流程必备规则全集验收",
        "来源规则熔入唯一新流程",
        "现成新编号入口门收点",
        "穷尽法补点判定",
        "姓名/别名/人物/对象归一",
        "空间/时间/季节归一",
        "多轴共现路由判定",
        "问题树与子问题拆解判定",
        "问题单元/子问题内两两比较方法判定",
        "编号收点",
        "图内交集路由",
        "聚拢层级放大/缩小",
        "原文裁判",
        "材料池入池凭证",
    ]
    if should_decompose:
        required_gates.extend(["问题树", "子问题出卷闸门"])
    required_gates.extend(["Codex 材料池判定", "必要补证循环"])
    required_gates.append("终稿后质量复核")

    return RuntimeDecision(
        question=question,
        should_decompose=should_decompose,
        decompose_reason=reason,
        fast_path_allowed=False,
        required_gates=required_gates,
        deep_mode_requested=deep_mode,
        comparison_method_requested=comparison_method,
        argument_unit_count=argument_unit_count,
        argument_units=argument_units,
    )


def route_context_entry_terms(route_context: str = "") -> tuple[dict[str, Any], list[str]]:
    if decomposer is None or not str(route_context or "").strip():
        return {}, []
    try:
        profile = decomposer.route_context_profile(route_context)
        if not isinstance(profile, dict):
            return {}, []
        terms = decomposer.primary_strategy_terms(profile)
        terms = [str(term).strip() for term in terms if str(term or "").strip()]
        return profile, list(dict.fromkeys(terms))
    except Exception as exc:  # pragma: no cover - keep runtime bus usable
        return {"status": "route_context_profile_failed", "error": str(exc)}, []


def build_runtime_bus_packet(question: str, route_context: str = "") -> dict[str, Any]:
    decision = decide_runtime_route(question)
    route_profile, route_entry_terms = route_context_entry_terms(route_context)
    graph_packet: Any = None
    if build_aggregation_graph_packet is not None:
        try:
            graph_packet = build_aggregation_graph_packet(
                question,
                terms=route_entry_terms or None,
            )
        except Exception as exc:  # pragma: no cover - defensive packet
            graph_packet = {"error": str(exc), "status": "aggregation_graph_failed"}

    two_layer_checkin: Any = None
    if build_two_layer_checkin_packet is not None:
        try:
            two_layer_checkin = build_two_layer_checkin_packet(
                question,
                graph_packet if isinstance(graph_packet, dict) else {},
            )
        except Exception as exc:  # pragma: no cover - defensive packet
            two_layer_checkin = {"error": str(exc), "status": "two_layer_checkin_failed"}

    selected_libraries: list[str] = []
    library_packet: Any = None
    if False and select_libraries is not None:
        try:
            library_packet = select_libraries(question)
            if isinstance(library_packet, dict):
                selected_libraries = [
                    str(item.get("library_id") or item.get("name") or item)
                    for item in library_packet.get("selected_libraries", [])
                ]
            elif isinstance(library_packet, list):
                selected_libraries = [str(item) for item in library_packet]
        except Exception as exc:  # pragma: no cover - defensive packet
            library_packet = {"error": str(exc), "status": "selector_failed"}

    eight_step_packet: Any = None
    if build_eight_step_packet is not None:
        try:
            eight_step_packet = build_eight_step_packet(question, selected_libraries)
        except Exception as exc:  # pragma: no cover - defensive packet
            eight_step_packet = {"error": str(exc), "status": "eight_step_failed"}

    return {
        "name": RUNTIME_BUS_NAME,
        "question": question,
        "route_context": route_context,
        "route_context_profile": route_profile,
        "route_context_entry_terms": route_entry_terms,
        "main_flow": RUNTIME_MAIN_FLOW,
        "shared_eight_step_spine": SHARED_EIGHT_STEP_SPINE,
        "shared_eight_step_formula": SHARED_EIGHT_STEP_FORMULA,
        "query_heads": QUERY_HEADS,
        "tool_difference_only": True,
        "route_decision": asdict(decision),
        "two_layer_checkin": two_layer_checkin,
        "aggregation_graph_packet": graph_packet,
        "library_selection": {
            "status": "sealed_as_front_door",
            "reason": "库分级选库不再作为运行前门；只在聚拢总图无命中、映射断裂、需要补漏时作为后台补点参考。",
            "legacy_selector_available": select_libraries is not None,
            "legacy_selector_output": library_packet,
        },
        "eight_step_packet": eight_step_packet,
        "legacy_front_gate_policy": {
            "old_candidate_hint_card": "封城；只能作为候选对象建议工具。",
            "old_search_terms": "只能作为穷尽法补点工具；补出来的编号必须回聚拢总图，不得直接入池或直接出答案。",
            "old_library_selector": "封为后台补点参考；不得作为第一前门。",
        },
        "new_flow_required_rule_set": new_flow_required_rule_set(),
        "new_flow_embedded_rules": [
            "姓名/别名/称谓归一：使用人物库、别名固化表、人物-段落映射库作为唯一新流程内的归一依据。",
            "库结构加载：使用 128 总入口、25 库登记处机器总表、红楼梦语义聚拢中心库_CH001_120.sqlite、红楼梦坐标查询中心库_CH001_120.sqlite 作为双中心取材入口；旧全文库只作后台回源/补点依据。",
            "复杂拆题：问题树、问题单元、子问题材料池和子问题出卷闸门已经熔入唯一新流程。",
            "两两比较/两组对照：只作为问题单元或子问题内部方法；必须有共同维度、同场对照、反证边界。",
            "全书穷尽查证/全文检索：只作为聚拢库内补点工具，补出的编号必须回聚拢总图。",
            "原文回证：chapters.full_text / segments 原文锚点是最终强结论来源。",
        ],
        "hard_block_rules": [
            "BLOCK: 无本题闭环包 package_dir，不得进入正文答案。",
            "BLOCK: 00AC/00AG/00AI/00AM 任一缺失，不得进入正文答案。",
            "BLOCK: 直接 SQLite、直接 FTS、旧搜索词网络不得作为运行前门。",
            "BLOCK: 后台补点产出的候选未回聚拢编号，不得入最终材料池。",
            "BLOCK: 复杂题无问题树和子问题过账，不得出卷。",
            "BLOCK: 已进入比较/对照的问题单元无共同维度、两两对照和反证边界记录，不得出卷。",
            "BLOCK: 无原文锚点或原文缺口记录，不得形成强结论。",
            "BLOCK: 唯一新流程必备规则全集未加载，不得进入正文答案。",
        ],
        "exit_contract": {
            "fast_path": "旧快速路径已关闭；简单题也必须先有 package_dir 与 00AC/00AG/00AI/00AM。",
            "complex_path": "复杂题必须逐子问题过账；子问题不过账，不准出卷。",
            "final_quality": "终稿必须过质量复核门。",
        },
    }


def render_runtime_bus_card(question: str, route_context: str = "") -> str:
    packet = build_runtime_bus_packet(question, route_context=route_context)
    decision = packet["route_decision"]
    route_terms = packet.get("route_context_entry_terms") if isinstance(packet.get("route_context_entry_terms"), list) else []
    graph_packet = packet.get("aggregation_graph_packet") if isinstance(packet.get("aggregation_graph_packet"), dict) else {}
    checkin = packet.get("two_layer_checkin") if isinstance(packet.get("two_layer_checkin"), dict) else {}
    exhaustive_tool = graph_packet.get("exhaustive_tool") if isinstance(graph_packet.get("exhaustive_tool"), dict) else {}
    existing_gate = graph_packet.get("existing_numbering_front_gate") if isinstance(graph_packet.get("existing_numbering_front_gate"), dict) else {}
    lines = [
        f"# {RUNTIME_BUS_NAME}执行卡",
        "",
        f"问题：{question}",
        "",
        "## 路由判定",
        "",
        f"- 是否拆成子问题：{'是' if decision['should_decompose'] else '否'}",
        f"- 理由：{decision['decompose_reason']}",
        f"- 深度要求：{'是' if decision.get('deep_mode_requested') else '否'}",
        f"- 比较/对照方法：{'是' if decision.get('comparison_method_requested') else '否'}",
        f"- 论证单元数：{decision.get('argument_unit_count', 0)}",
        f"- route_context入口词：{'、'.join(route_terms) or '无'}",
        f"- 是否允许快速路径：否（旧流程已关闭）",
        f"- 双打卡状态：{checkin.get('status', '未接入')}",
        f"- 双打卡是否可继续：{'是' if checkin.get('allow_continue') else '否'}",
        "",
        "## 双头共用八步主线",
        "",
        f"- 共同主线：{packet.get('shared_eight_step_formula', SHARED_EIGHT_STEP_FORMULA)}",
        f"- 工具差异限定：{'是' if packet.get('tool_difference_only') else '否'}",
    ]
    for head, config in (packet.get("query_heads") or {}).items():
        if isinstance(config, dict):
            lines.append(f"- {head}：{config.get('tooling', '')}")
    lines.extend(
        [
        "",
        "## 新前门",
        "",
        f"- 前门：{graph_packet.get('graph_short_name', '聚拢总图')}",
        f"- 公式：{graph_packet.get('runtime_formula', '库先入图，AI 再查图，图再回原文。')}",
        f"- 现成编号入口门：{existing_gate.get('status', '未调用')}",
        f"- 穷尽法：{exhaustive_tool.get('existing_tool_module', 'formal_honglou_numbering_front_gate.py')} / {exhaustive_tool.get('existing_collect_method', '全文穷尽收点')}",
        "",
        "## 必经闸门",
        ]
    )
    lines.extend(f"- {gate}" for gate in decision["required_gates"])
    lines.extend(
        [
            "",
            "## 唯一新流程必备规则全集",
            "",
        ]
    )
    for idx, row in enumerate(packet.get("new_flow_required_rule_set", []), start=1):
        if isinstance(row, dict):
            lines.extend(
                [
                    f"### {idx}. {row.get('rule_id', '')}",
                    "",
                    f"- 来源依据：{row.get('source_basis', '')}",
                    f"- 新流程规则：{row.get('required_rule', '')}",
                    f"- 唯一落点：{row.get('flow_slot', '')}",
                    f"- 执行方式：{row.get('enforcement', '')}",
                    f"- 验收凭证：{row.get('acceptance_evidence', '')}",
                    f"- 旧执行路权：{row.get('old_execution_permission', '')}",
                    f"- 阻断条件：{row.get('block_rule', '')}",
                    "",
                ]
            )
    lines.extend(["", "## 规则全集上岗"])
    lines.extend(f"- {item}" for item in packet.get("new_flow_embedded_rules", []))
    lines.extend(["", "## 硬阻断条件"])
    lines.extend(f"- {item}" for item in packet.get("hard_block_rules", []))
    lines.extend(["", "## 主流程"])
    lines.extend(f"{idx}. {stage}" for idx, stage in enumerate(RUNTIME_MAIN_FLOW, start=1))
    lines.extend(
        [
            "",
            "## 硬规则",
            "",
            "- 候选提示类资料封存为后台候选建议，不得作为前门。",
            "- 搜索词补点只能作为穷尽法补编号，不能直接入池。",
            "- 库分级选库封为后台参考，不能作为运行前门。",
            "- 穷尽法补出来的编号必须回聚拢总图。",
            "- 简单题不强拆，但必须先建本题闭环包并过聚拢四件套。",
            "- 复杂题不裸答。",
            "- 子问题不过账，不准出卷。",
            "- 终稿必须过质量复核门。",
        ]
    )
    return "\n".join(lines) + "\n"
