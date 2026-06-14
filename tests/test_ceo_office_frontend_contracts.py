from pathlib import Path


FRONTEND_SRC = Path("web/frontend/src")


def read_frontend(path: str) -> str:
    return (FRONTEND_SRC / path).read_text(encoding="utf-8")


def test_router_makes_ceo_office_home_and_moves_market_to_market_route():
    router = read_frontend("router/index.ts")

    assert '{ path: "/", name: "ceo-office", component: () => import("../views/CEOOffice.vue") }' in router
    assert '{ path: "/market", name: "market", component: () => import("../views/Market.vue") }' in router
    assert '{ path: "/", name: "market", component: () => import("../views/Market.vue") }' not in router


def test_app_shell_nav_exposes_ceo_office_and_market_separately():
    app = read_frontend("App.vue")
    zh_nav = read_frontend("i18n/messages/zh-CN/nav.ts")
    en_nav = read_frontend("i18n/messages/en-US/nav.ts")

    assert 'path: "/", labelKey: "nav.ceoOffice"' in app
    assert 'path: "/market", labelKey: "nav.market"' in app
    assert 'if (route.path.startsWith("/market")) return "/market";' in app
    assert 'ceoOffice: "CEO 办公室"' in zh_nav
    assert 'ceoOffice: "CEO Office"' in en_nav


def test_ceo_office_view_uses_agent_api_and_i18n():
    view = read_frontend("views/CEOOffice.vue")
    zh_index = read_frontend("i18n/messages/zh-CN/index.ts")
    en_index = read_frontend("i18n/messages/en-US/index.ts")
    zh_ceo = read_frontend("i18n/messages/zh-CN/ceoOffice.ts")
    en_ceo = read_frontend("i18n/messages/en-US/ceoOffice.ts")

    assert "useI18n" in view
    assert "api.agentSessions" in view
    assert "api.agentDesks" in view
    assert "api.agentCreateSession" in view
    assert "api.agentUpdateSession" in view
    assert "api.agentAddMessage" in view
    assert "api.agentAction" in view
    assert "api.agentRunAction" in view
    assert "api.agentCancelAction" in view
    assert "selectedAction" in view
    assert "cancelAction" in view
    assert "canCancelAction" in view
    assert "archiveSession" in view
    assert "archivingSession" in view
    assert "selectedEvidence" in view
    assert "selectedEvidenceNavigation" in view
    assert "openLinkedView" in view
    assert "handoffs" in view
    assert "api.agentHandoffs" in view
    assert "api.agentResolveHandoff" in view
    assert "resolveHandoff" in view
    assert "ceoOffice" in zh_index
    assert "ceoOffice" in en_index
    assert "行动队列" in zh_ceo
    assert "Action Queue" in en_ceo
    assert "归档会话" in zh_ceo
    assert "Archive Session" in en_ceo
    assert "交接事项" in zh_ceo
    assert "标记完成" in zh_ceo
    assert "Handoffs" in en_ceo
    assert "Resolve" in en_ceo
    assert "取消行动" in zh_ceo
    assert "已取消" in zh_ceo
    assert "Cancel Action" in en_ceo
    assert "Canceled" in en_ceo
    assert "证据详情" in zh_ceo
    assert "打开关联视图" in zh_ceo
    assert "Evidence Detail" in en_ceo
    assert "Open Linked View" in en_ceo


def test_frontend_agent_api_module_exports_runtime_types_and_calls():
    api_index = read_frontend("api/index.ts")
    api_types = read_frontend("api/types.ts")
    agent_api = read_frontend("api/modules/agent.ts")
    agent_types = read_frontend("api/types/agent.ts")

    assert "agentApi" in api_index
    assert 'export * from "./types/agent";' in api_types
    assert "agentSessions" in agent_api
    assert "agentCreateSession" in agent_api
    assert "agentUpdateSession" in agent_api
    assert "agentActions" in agent_api
    assert "agentApproveAction" in agent_api
    assert "agentRejectAction" in agent_api
    assert "agentCancelAction" in agent_api
    assert "agentRunAction" in agent_api
    assert "agentHandoffs" in agent_api
    assert "agentResolveHandoff" in agent_api
    assert "export interface AgentSession" in agent_types
    assert "export interface AgentAction" in agent_types
    assert "export interface AgentActionDetail" in agent_types
    assert "export interface AgentHandoff" in agent_types
    assert "export interface EvidenceRef" in agent_types
    assert "export interface EvidenceNavigation" in agent_types
    assert "navigation: EvidenceNavigation | null" in agent_types
