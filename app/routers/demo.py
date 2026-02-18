from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/demo", response_class=HTMLResponse)
async def demo_ui():
    """
    Demo UI for the conversational chatbot with booking support.
    Features: persistent session, dynamic action buttons, booking flow.
    """
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Nova Clinic - Chat Assistant</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
        <style>
            :root {
                --teal: #32b4a4;
                --teal-light: #5ec6b8;
                --teal-dark: #28a090;
                --navy: #1e3a5f;
                --navy-dark: #152d4a;
                --slate: #1e293b;
                --gray-50: #f8fafc;
                --gray-100: #f1f5f9;
                --gray-200: #e2e8f0;
                --gray-300: #cbd5e1;
                --gray-400: #94a3b8;
                --gray-500: #64748b;
                --gray-600: #475569;
                --white: #ffffff;
                --radius: 16px;
                --radius-sm: 10px;
                --radius-full: 9999px;
                --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
                --shadow: 0 4px 6px -1px rgba(0,0,0,0.07), 0 2px 4px -2px rgba(0,0,0,0.05);
                --shadow-lg: 0 20px 50px -12px rgba(0,0,0,0.15);
                --shadow-xl: 0 25px 60px -15px rgba(26,75,110,0.25);
            }

            * { margin: 0; padding: 0; box-sizing: border-box; }

            body {
                font-family: 'SF Pro Display', 'SF Pro Text', -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', Helvetica, sans-serif;
                background: linear-gradient(135deg, #e8f4f2 0%, #e2e8f0 50%, #ede9f6 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 16px;
                -webkit-font-smoothing: antialiased;
                -moz-osx-font-smoothing: grayscale;
                letter-spacing: 0.01em;
            }

            /* ── Container ───────────────────────────────────── */
            .container {
                width: 100%;
                max-width: 520px;
                background: rgba(255, 255, 255, 0.72);
                backdrop-filter: blur(20px);
                -webkit-backdrop-filter: blur(20px);
                border-radius: var(--radius);
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.08), 0 0 0 1px rgba(255,255,255,0.5) inset;
                overflow: hidden;
                display: flex;
                flex-direction: column;
                height: 92vh;
                border: 1px solid rgba(255, 255, 255, 0.6);
            }

            /* ── Header ──────────────────────────────────────── */
            .header {
                background: rgba(255, 255, 255, 0.65);
                backdrop-filter: blur(16px);
                -webkit-backdrop-filter: blur(16px);
                padding: 16px 20px;
                display: flex;
                align-items: center;
                gap: 14px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.5);
            }
            .header-logo {
                height: 40px;
                width: auto;
                flex-shrink: 0;
            }
            .header-text { flex: 1; }
            .header-title {
                font-size: 15px;
                font-weight: 600;
                color: var(--navy);
                letter-spacing: -0.3px;
            }
            .header-subtitle {
                font-size: 12px;
                color: var(--gray-500);
                margin-top: 1px;
            }
            .header-status {
                width: 8px;
                height: 8px;
                background: #22c55e;
                border-radius: 50%;
                flex-shrink: 0;
                box-shadow: 0 0 0 3px rgba(34,197,94,0.2);
            }
            .header-refresh {
                width: 32px;
                height: 32px;
                border: none;
                background: rgba(255, 255, 255, 0.4);
                border-radius: 50%;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
                transition: all 0.2s;
                color: var(--gray-500);
            }
            .header-refresh:hover {
                background: rgba(255, 255, 255, 0.65);
                color: var(--teal);
                transform: rotate(90deg);
            }
            .header-refresh svg {
                width: 16px;
                height: 16px;
            }

            /* ── Chat area ───────────────────────────────────── */
            .chat-container {
                flex: 1;
                overflow-y: auto;
                padding: 24px 18px;
                background: transparent;
                scroll-behavior: smooth;
            }
            .chat-container::-webkit-scrollbar { width: 4px; }
            .chat-container::-webkit-scrollbar-track { background: transparent; }
            .chat-container::-webkit-scrollbar-thumb {
                background: rgba(0,0,0,0.12);
                border-radius: 4px;
            }

            /* ── Messages ────────────────────────────────────── */
            .message {
                margin-bottom: 20px;
                animation: msgIn 0.3s ease-out;
                display: flex;
                align-items: flex-end;
                gap: 10px;
            }
            @keyframes msgIn {
                from { opacity: 0; transform: translateY(8px); }
                to { opacity: 1; transform: translateY(0); }
            }
            .message.user { justify-content: flex-end; }

            .message-avatar {
                width: 30px;
                height: 30px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
                font-size: 11px;
                font-weight: 600;
                color: var(--white);
            }
            .message.assistant .message-avatar {
                background: linear-gradient(135deg, rgba(50,180,164,0.85), rgba(30,58,95,0.85));
            }
            .message.user .message-avatar {
                background: var(--gray-400);
                order: 2;
            }

            .message-body {
                max-width: 88%;
                display: flex;
                flex-direction: column;
            }
            .message.user .message-body { align-items: flex-end; }

            .message-content {
                padding: 12px 16px;
                border-radius: 18px;
                word-wrap: break-word;
                line-height: 1.6;
                white-space: pre-wrap;
                font-size: 14px;
            }
            .message.user .message-content {
                background: var(--navy);
                color: var(--white);
                border-bottom-right-radius: 4px;
            }
            .message.assistant .message-content {
                background: rgba(255, 255, 255, 0.6);
                backdrop-filter: blur(12px);
                -webkit-backdrop-filter: blur(12px);
                color: var(--slate);
                border: 1px solid rgba(255, 255, 255, 0.5);
                border-bottom-left-radius: 4px;
                box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
            }

            /* ── Confidence badges ───────────────────────────── */
            .confidence-badge {
                display: inline-block;
                padding: 2px 8px;
                border-radius: var(--radius-full);
                font-size: 10px;
                font-weight: 500;
                margin-top: 8px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            .confidence-high { background: #dcfce7; color: #166534; }
            .confidence-medium { background: #fef9c3; color: #854d0e; }
            .confidence-low { background: #fee2e2; color: #991b1b; }

            /* ── Citations ───────────────────────────────────── */
            .citations {
                margin-top: 10px;
                padding: 10px;
                background: rgba(248, 250, 252, 0.5);
                border-radius: var(--radius-sm);
                font-size: 12px;
                border-left: 3px solid var(--teal);
            }
            .citations h4 {
                font-size: 10px;
                color: var(--gray-500);
                margin-bottom: 6px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                font-weight: 600;
            }
            .citation-item {
                padding: 4px 0;
                border-bottom: 1px solid var(--gray-200);
                color: var(--gray-600);
            }
            .citation-item:last-child { border-bottom: none; }
            .citation-item strong { color: var(--teal); font-weight: 600; }

            /* ── Feedback ────────────────────────────────────── */
            .feedback-buttons { margin-top: 8px; display: flex; gap: 2px; }
            .feedback-btn {
                background: transparent;
                border: none;
                padding: 4px;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--gray-400);
                transition: all 0.15s;
                border-radius: 6px;
            }
            .feedback-btn:hover { color: var(--teal); background: var(--gray-50); }
            .feedback-btn.active-up { color: #22c55e; }
            .feedback-btn.active-down { color: #ef4444; }

            /* ── Action buttons ───────────────────────────────── */
            .actions-row {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                margin-top: 12px;
            }
            .patient-card + .actions-row,
            .verify-card + .actions-row {
                margin-top: 16px;
            }
            .action-btn {
                padding: 9px 16px;
                border-radius: var(--radius-full);
                cursor: pointer;
                font-size: 12.5px;
                font-weight: 400;
                transition: all 0.2s ease;
                border: none;
                font-family: inherit;
            }
            .action-btn:hover {
                transform: translateY(-1px);
                box-shadow: var(--shadow);
            }
            .action-btn.quick_reply {
                background: rgba(255, 255, 255, 0.5);
                backdrop-filter: blur(8px);
                -webkit-backdrop-filter: blur(8px);
                border: 1px solid rgba(255, 255, 255, 0.6);
                color: var(--slate);
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
            }
            .action-btn.quick_reply:hover {
                background: rgba(255, 255, 255, 0.75);
                border-color: rgba(255, 255, 255, 0.8);
                color: var(--teal-dark);
            }
            .action-btn.booking {
                background: rgba(50, 180, 164, 0.85);
                backdrop-filter: blur(8px);
                -webkit-backdrop-filter: blur(8px);
                border: 1px solid rgba(255, 255, 255, 0.25);
                color: var(--white);
                box-shadow: 0 4px 16px rgba(50, 180, 164, 0.2);
            }
            .action-btn.back {
                background: transparent;
                border: 1.5px dashed var(--gray-300);
                color: var(--gray-500);
                font-size: 11px;
            }
            .action-btn.back:hover {
                border-color: var(--gray-400);
                color: var(--gray-700);
                background: var(--gray-50);
                transform: none;
                box-shadow: none;
            }
            .action-btn.booking:hover {
                background: rgba(50, 180, 164, 0.95);
                box-shadow: 0 6px 20px rgba(50, 180, 164, 0.3);
            }

            /* ── Welcome buttons ──────────────────────────────── */
            .welcome-actions {
                margin-left: 38px;
                margin-top: -8px;
                margin-bottom: 16px;
            }
            .welcome-grid {
                display: flex;
                flex-wrap: wrap;
                gap: 6px;
            }
            .welcome-btn {
                background: rgba(255, 255, 255, 0.5);
                backdrop-filter: blur(8px);
                -webkit-backdrop-filter: blur(8px);
                border: 1px solid rgba(255, 255, 255, 0.6);
                padding: 10px 18px;
                border-radius: var(--radius-sm);
                cursor: pointer;
                font-size: 13px;
                font-weight: 400;
                color: var(--slate);
                transition: all 0.15s;
                font-family: inherit;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
            }
            .welcome-btn:hover {
                background: rgba(255, 255, 255, 0.75);
                color: var(--teal-dark);
                border-color: rgba(255, 255, 255, 0.8);
                transform: translateY(-1px);
                box-shadow: 0 4px 12px rgba(0,0,0,0.06);
            }

            /* ── Service categories ───────────────────────────── */
            .services-list {
                display: flex;
                flex-direction: column;
                gap: 4px;
                margin-top: 8px;
                width: 100%;
            }
            .service-category {
                border: 1px solid rgba(255, 255, 255, 0.5);
                border-radius: var(--radius-sm);
                background: rgba(255, 255, 255, 0.45);
                backdrop-filter: blur(8px);
                -webkit-backdrop-filter: blur(8px);
                overflow: hidden;
                transition: all 0.2s;
            }
            .service-category.expanded {
                border-color: rgba(50, 180, 164, 0.4);
                box-shadow: 0 2px 12px rgba(50,180,164,0.1);
            }
            .category-header {
                padding: 9px 12px;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: space-between;
                transition: all 0.15s;
                font-size: 12px;
                font-weight: 500;
                color: var(--slate);
            }
            .category-header:hover { background: rgba(255, 255, 255, 0.4); }
            .service-category.expanded .category-header {
                background: linear-gradient(135deg, rgba(50,180,164,0.85) 0%, rgba(30,58,95,0.85) 100%);
                color: var(--white);
            }
            .category-arrow {
                font-size: 9px;
                transition: transform 0.2s;
                opacity: 0.6;
            }
            .service-category.expanded .category-arrow {
                transform: rotate(90deg);
                opacity: 1;
            }
            .sub-services {
                display: none;
                padding: 4px 8px 8px;
                border-top: 1px solid rgba(255, 255, 255, 0.4);
            }
            .service-category.expanded .sub-services { display: block; }
            .sub-service-btn {
                display: block;
                width: 100%;
                text-align: left;
                padding: 7px 10px;
                margin-top: 3px;
                border-radius: 6px;
                cursor: pointer;
                font-size: 12px;
                font-weight: 400;
                border: none;
                background: rgba(248, 250, 252, 0.5);
                color: var(--gray-600);
                transition: all 0.15s;
                font-family: inherit;
            }
            .sub-service-btn:hover {
                background: rgba(224, 242, 241, 0.6);
                color: var(--teal-dark);
            }
            .sub-service-btn:disabled {
                opacity: 0.5;
                cursor: default;
            }
            .sub-detail {
                font-weight: 400;
                color: var(--gray-400);
                font-size: 11px;
                margin-left: 4px;
            }

            /* ── Input ───────────────────────────────────────── */
            .input-container {
                padding: 12px 16px;
                background: rgba(255, 255, 255, 0.65);
                backdrop-filter: blur(16px);
                -webkit-backdrop-filter: blur(16px);
                border-top: 1px solid rgba(255, 255, 255, 0.5);
                display: flex;
                gap: 8px;
                align-items: center;
            }
            #questionInput {
                flex: 1;
                padding: 10px 16px;
                border: 1px solid rgba(0, 0, 0, 0.06);
                border-radius: var(--radius-full);
                font-size: 14px;
                outline: none;
                transition: all 0.15s;
                font-family: inherit;
                background: rgba(248, 250, 252, 0.6);
                backdrop-filter: blur(8px);
                -webkit-backdrop-filter: blur(8px);
                color: var(--slate);
            }
            #questionInput::placeholder { color: var(--gray-400); }
            #questionInput:focus {
                border-color: var(--teal);
                background: var(--white);
                box-shadow: 0 0 0 3px rgba(42,157,143,0.1);
            }
            #sendButton {
                width: 40px;
                height: 40px;
                background: rgba(50, 180, 164, 0.9);
                backdrop-filter: blur(8px);
                -webkit-backdrop-filter: blur(8px);
                color: var(--white);
                border: none;
                border-radius: 50%;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: all 0.15s;
                flex-shrink: 0;
                box-shadow: 0 4px 16px rgba(50, 180, 164, 0.25);
            }
            #sendButton:hover {
                transform: translateY(-1px);
                box-shadow: 0 6px 20px rgba(50, 180, 164, 0.35);
            }
            #sendButton:active { transform: translateY(0); }
            #sendButton:disabled {
                opacity: 0.5;
                cursor: not-allowed;
                transform: none;
            }
            #sendButton svg {
                width: 18px;
                height: 18px;
            }

            .loading {
                display: inline-block;
                width: 16px; height: 16px;
                border: 2px solid rgba(255,255,255,0.3);
                border-radius: 50%;
                border-top-color: var(--white);
                animation: spin 0.6s linear infinite;
            }
            @keyframes spin { to { transform: rotate(360deg); } }

            /* ── Typing indicator ─────────────────────────────── */
            .typing-indicator {
                display: inline-block;
                padding: 10px 14px;
                background: rgba(255, 255, 255, 0.6);
                backdrop-filter: blur(12px);
                -webkit-backdrop-filter: blur(12px);
                border-radius: 16px;
                border-bottom-left-radius: 4px;
                box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.5);
            }
            .typing-indicator span {
                height: 6px; width: 6px;
                background: var(--gray-400);
                border-radius: 50%;
                display: inline-block;
                margin: 0 1.5px;
                animation: bounce 1.4s infinite ease-in-out both;
            }
            .typing-indicator span:nth-child(1) { animation-delay: -0.32s; }
            .typing-indicator span:nth-child(2) { animation-delay: -0.16s; }
            @keyframes bounce {
                0%, 80%, 100% { transform: scale(0); }
                40% { transform: scale(1); }
            }

            /* ── Powered-by footer ───────────────────────────── */
            .powered-by {
                text-align: center;
                padding: 6px;
                font-size: 10px;
                color: var(--gray-400);
                background: transparent;
                border-top: 1px solid rgba(255, 255, 255, 0.3);
                letter-spacing: 0.3px;
            }

            /* ── Verification form card ──────────────────────── */
            .verify-card {
                background: rgba(255, 255, 255, 0.55);
                backdrop-filter: blur(12px);
                -webkit-backdrop-filter: blur(12px);
                border: 1px solid rgba(255, 255, 255, 0.5);
                border-radius: 20px;
                overflow: hidden;
                margin-top: 14px;
                width: 100%;
                box-shadow: 0 8px 30px -6px rgba(0,0,0,0.08), 0 2px 8px -2px rgba(0,0,0,0.04);
            }
            .verify-card.disabled {
                opacity: 0.45;
                pointer-events: none;
                filter: grayscale(0.3);
            }
            .verify-card-header {
                background: linear-gradient(135deg, rgba(50,180,164,0.85) 0%, rgba(30,58,95,0.85) 100%);
                padding: 16px 24px;
                display: flex;
                align-items: center;
                gap: 10px;
                color: var(--white);
                font-size: 13.5px;
                font-weight: 500;
                letter-spacing: 0.2px;
            }
            .verify-card-header svg {
                width: 16px;
                height: 16px;
                flex-shrink: 0;
                opacity: 0.85;
            }
            .verify-form-body {
                padding: 24px;
            }
            .verify-form-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 18px;
            }
            .verify-field {
                display: flex;
                flex-direction: column;
                gap: 6px;
                min-width: 0;
            }
            .verify-label {
                font-size: 10px;
                font-weight: 600;
                color: var(--gray-400);
                text-transform: uppercase;
                letter-spacing: 0.8px;
                padding-left: 2px;
            }
            .verify-input {
                padding: 11px 14px;
                border: 1px solid rgba(0, 0, 0, 0.06);
                border-radius: 10px;
                font-size: 13.5px;
                font-family: inherit;
                color: var(--slate);
                background: rgba(248, 250, 252, 0.6);
                outline: none;
                transition: all 0.2s ease;
                width: 100%;
                box-sizing: border-box;
            }
            .verify-input::placeholder {
                color: var(--gray-400);
                font-weight: 400;
            }
            .verify-input:focus {
                border-color: var(--teal);
                background: var(--white);
                box-shadow: 0 0 0 3px rgba(42,157,143,0.1);
            }
            .verify-input.error {
                border-color: #ef4444;
                box-shadow: 0 0 0 3px rgba(239,68,68,0.1);
            }
            .verify-actions {
                display: flex;
                align-items: center;
                gap: 10px;
                margin-top: 22px;
            }
            .verify-submit-btn {
                flex: 1;
                padding: 12px 20px;
                background: rgba(50, 180, 164, 0.85);
                backdrop-filter: blur(8px);
                -webkit-backdrop-filter: blur(8px);
                color: var(--white);
                border: 1px solid rgba(255, 255, 255, 0.25);
                border-radius: 10px;
                font-size: 13.5px;
                font-weight: 500;
                font-family: inherit;
                cursor: pointer;
                transition: all 0.2s ease;
                box-shadow: 0 4px 16px rgba(50, 180, 164, 0.2);
                letter-spacing: 0.1px;
            }
            .verify-submit-btn:hover {
                transform: translateY(-1px);
                box-shadow: 0 6px 20px rgba(50, 180, 164, 0.3);
            }
            .verify-submit-btn:active {
                transform: translateY(0);
            }
            .verify-guest-btn {
                padding: 12px 22px;
                background: rgba(255, 255, 255, 0.5);
                backdrop-filter: blur(8px);
                -webkit-backdrop-filter: blur(8px);
                border: 1px solid rgba(255, 255, 255, 0.6);
                border-radius: 10px;
                font-size: 13px;
                font-weight: 400;
                font-family: inherit;
                color: var(--gray-500);
                cursor: pointer;
                transition: all 0.2s ease;
            }
            .verify-guest-btn:hover {
                background: rgba(255, 255, 255, 0.75);
                border-color: rgba(255, 255, 255, 0.8);
                color: var(--slate);
            }

            /* ── Patient profile card ───────────────────────────── */
            .patient-card {
                background: rgba(255, 255, 255, 0.55);
                backdrop-filter: blur(12px);
                -webkit-backdrop-filter: blur(12px);
                border: 1px solid rgba(255, 255, 255, 0.5);
                border-radius: 20px;
                overflow: hidden;
                margin-top: 14px;
                width: 100%;
                box-shadow: 0 8px 30px -6px rgba(0,0,0,0.08), 0 2px 8px -2px rgba(0,0,0,0.04);
            }
            .patient-card-header {
                background: linear-gradient(135deg, rgba(50,180,164,0.85) 0%, rgba(30,107,138,0.85) 50%, rgba(30,58,95,0.85) 100%);
                padding: 20px 22px;
                display: flex;
                align-items: center;
                gap: 16px;
                color: var(--white);
            }
            .patient-avatar {
                width: 50px;
                height: 50px;
                border-radius: 50%;
                background: rgba(255,255,255,0.18);
                backdrop-filter: blur(4px);
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: 600;
                font-size: 16px;
                flex-shrink: 0;
                border: 2.5px solid rgba(255,255,255,0.3);
                letter-spacing: 0.5px;
            }
            .patient-header-text { flex: 1; }
            .patient-name {
                font-size: 17px;
                font-weight: 600;
                letter-spacing: -0.3px;
            }
            .patient-badge {
                display: inline-flex;
                align-items: center;
                gap: 5px;
                margin-top: 6px;
                font-size: 10px;
                font-weight: 500;
                text-transform: uppercase;
                letter-spacing: 0.6px;
                background: rgba(255,255,255,0.18);
                padding: 4px 10px;
                border-radius: var(--radius-full);
            }
            .patient-badge svg { width: 11px; height: 11px; }
            .patient-info-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 1px;
                background: rgba(0, 0, 0, 0.04);
            }
            .patient-info-item {
                padding: 16px 20px;
                background: rgba(255, 255, 255, 0.5);
            }
            .patient-info-item.full-width { grid-column: 1 / -1; }
            .info-label {
                font-size: 10px;
                font-weight: 600;
                color: var(--gray-400);
                text-transform: uppercase;
                letter-spacing: 0.6px;
                margin-bottom: 6px;
            }
            .info-value {
                font-size: 13.5px;
                font-weight: 500;
                color: var(--slate);
                line-height: 1.4;
            }
            .info-value.highlight {
                color: var(--teal-dark);
                font-weight: 600;
            }

            /* ── Responsive ──────────────────────────────────── */
            @media (max-width: 520px) {
                body { padding: 0; }
                .container {
                    max-width: 100%;
                    height: 100vh;
                    border-radius: 0;
                    border: none;
                }
                .verify-form-grid {
                    grid-template-columns: 1fr;
                    gap: 14px;
                }
                .patient-info-grid {
                    grid-template-columns: 1fr;
                }
                .message-body { max-width: 92%; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <img src="/static/logo.webp" alt="Nova Clinic" class="header-logo" />
                <div class="header-text">
                    <div class="header-title">Nova Assistant</div>
                    <div class="header-subtitle">Online now</div>
                </div>
                <div class="header-status"></div>
                <button class="header-refresh" onclick="resetChat()" title="New conversation">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
                </button>
            </div>

            <div class="chat-container" id="chatContainer">
                <div class="message assistant">
                    <div class="message-avatar">N</div>
                    <div class="message-body">
                        <div class="message-content">Welcome to Nova Clinic! I'm Nova, your personal AI assistant. Before we begin — are you a new patient, or have you visited us before?</div>
                    </div>
                </div>
                <div class="welcome-actions" id="welcomeActions">
                    <div class="welcome-grid">
                        <button class="welcome-btn" onclick="handlePatientType('new')">I'm a New Patient</button>
                        <button class="welcome-btn" onclick="handlePatientType('returning')">I'm a Returning Patient</button>
                    </div>
                </div>
            </div>

            <div class="input-container">
                <input
                    type="text"
                    id="questionInput"
                    placeholder="Ask me anything..."
                    onkeypress="if(event.key==='Enter') sendMessage()"
                />
                <button id="sendButton" onclick="sendMessage()">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
                </button>
            </div>
            <div class="powered-by">Powered by xtnsion.ai</div>
        </div>

        <script>
            // Persistent session ID
            let sessionId = crypto.randomUUID();
            let lastResponse = null;
            let welcomeHidden = false;

            function resetChat() {
                sessionId = crypto.randomUUID();
                lastResponse = null;
                welcomeHidden = false;
                const container = document.getElementById('chatContainer');
                container.innerHTML = '<div class="message assistant">'
                    + '<div class="message-avatar">N</div>'
                    + '<div class="message-body">'
                    + '<div class="message-content">Welcome to Nova Clinic! I\\'m Nova, your personal AI assistant. Before we begin — are you a new patient, or have you visited us before?</div>'
                    + '</div></div>'
                    + '<div class="welcome-actions" id="welcomeActions"><div class="welcome-grid">'
                    + '<button class="welcome-btn" onclick="handlePatientType(\\'new\\')">I\\'m a New Patient</button>'
                    + '<button class="welcome-btn" onclick="handlePatientType(\\'returning\\')">I\\'m a Returning Patient</button>'
                    + '</div></div>';
                document.getElementById('questionInput').value = '';
                document.getElementById('questionInput').focus();
            }

            function hideWelcome() {
                if (welcomeHidden) return;
                welcomeHidden = true;
                const el = document.getElementById('welcomeActions');
                if (el) el.style.display = 'none';
            }

            function handlePatientType(type) {
                if (type === 'returning') {
                    showVerificationForm();
                    return;
                }
                const msg = "I'm a new patient";
                document.getElementById('questionInput').value = msg;
                sendMessage();
            }

            function showVerificationForm() {
                hideWelcome();
                const container = document.getElementById('chatContainer');

                // User bubble
                const userDiv = document.createElement('div');
                userDiv.className = 'message user';
                userDiv.innerHTML = '<div class="message-avatar"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg></div>'
                    + '<div class="message-body"><div class="message-content">I\\'m a Returning Patient</div></div>';
                container.appendChild(userDiv);

                // Assistant message with form card
                const assistantDiv = document.createElement('div');
                assistantDiv.className = 'message assistant';
                assistantDiv.innerHTML = '<div class="message-avatar">N</div>'
                    + '<div class="message-body">'
                    + '<div class="message-content">Welcome back! Let me pull up your account.</div>'
                    + '<div class="verify-card" id="verifyCard">'
                    + '<div class="verify-card-header">'
                    + '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>'
                    + '<span>Verify Your Account</span>'
                    + '</div>'
                    + '<div class="verify-form-body">'
                    + '<div class="verify-form-grid">'
                    + '<div class="verify-field">'
                    + '<label class="verify-label">Full Name</label>'
                    + '<input class="verify-input" id="verifyName" placeholder="e.g. Sarah Thompson" />'
                    + '</div>'
                    + '<div class="verify-field">'
                    + '<label class="verify-label">Phone Number</label>'
                    + '<input class="verify-input" id="verifyPhone" placeholder="(587) 555-0142" />'
                    + '</div>'
                    + '</div>'
                    + '<div class="verify-actions">'
                    + '<button class="verify-submit-btn" onclick="submitVerification()">Verify & Continue</button>'
                    + '<button class="verify-guest-btn" onclick="continueAsGuest()">Guest</button>'
                    + '</div>'
                    + '</div>'
                    + '</div>'
                    + '</div>';
                container.appendChild(assistantDiv);
                container.scrollTop = container.scrollHeight;

                // Focus the name field
                setTimeout(function() {
                    var nameInput = document.getElementById('verifyName');
                    if (nameInput) nameInput.focus();
                }, 100);
            }

            async function submitVerification() {
                var nameInput = document.getElementById('verifyName');
                var phoneInput = document.getElementById('verifyPhone');
                var phone = phoneInput.value.trim();

                if (!phone) {
                    phoneInput.classList.add('error');
                    phoneInput.focus();
                    return;
                }
                phoneInput.classList.remove('error');

                // Disable form
                var card = document.getElementById('verifyCard');
                card.classList.add('disabled');

                var container = document.getElementById('chatContainer');
                var typingId = addTypingIndicator();

                try {
                    // Step 1: Set returning patient state
                    await fetch('/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ message: "I'm a returning patient", session_id: sessionId })
                    });

                    // Step 2: Send phone for verification
                    var resp = await fetch('/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ message: phone, session_id: sessionId })
                    });

                    if (!resp.ok) throw new Error('Failed');
                    var data = await resp.json();

                    lastResponse = { question: phone, answer: data.answer, citations: data.citations };
                    removeTypingIndicator(typingId);
                    addMessage(data.answer, 'assistant', data.citations, data.confidence, data.max_similarity, data.actions || []);
                } catch (error) {
                    console.error('Verification error:', error);
                    removeTypingIndicator(typingId);
                    addMessage('Sorry, something went wrong. Please try again!', 'assistant');
                    card.classList.remove('disabled');
                }
            }

            async function continueAsGuest() {
                var card = document.getElementById('verifyCard');
                card.classList.add('disabled');

                var typingId = addTypingIndicator();

                try {
                    // Step 1: Set returning patient state
                    await fetch('/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ message: "I'm a returning patient", session_id: sessionId })
                    });

                    // Step 2: Continue as guest
                    var resp = await fetch('/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ message: "continue as guest", session_id: sessionId })
                    });

                    if (!resp.ok) throw new Error('Failed');
                    var data = await resp.json();

                    lastResponse = { question: 'continue as guest', answer: data.answer, citations: data.citations };
                    removeTypingIndicator(typingId);
                    addMessage(data.answer, 'assistant', data.citations, data.confidence, data.max_similarity, data.actions || []);
                } catch (error) {
                    console.error('Guest error:', error);
                    removeTypingIndicator(typingId);
                    addMessage('Welcome back! How can I help you today?', 'assistant');
                }
            }

            const SERVICE_CATEGORIES = [
                {
                    name: 'Naturopathic Medicine',
                    items: [
                        { label: 'Initial Consultation', detail: '~80 min, $295' },
                        { label: 'Follow-Up Appointment', detail: '15-60 min, $90-$225' },
                        { label: 'Pediatric Naturopathic', detail: 'Infants, children & adolescents' },
                        { label: 'Meet & Greet', detail: 'Free, 15 min' },
                    ]
                },
                {
                    name: 'IV Nutrient Therapy',
                    items: [
                        { label: 'Initial IV Consultation', detail: '~80 min, from $290' },
                        { label: 'IV Drip Sessions', detail: '45 min-2 hrs, $85-$195' },
                        { label: 'IV Push Sessions', detail: '15-45 min, $65-$115' },
                    ]
                },
                {
                    name: 'Injection Therapy & Prolotherapy',
                    items: [
                        { label: 'Initial Injection Consultation', detail: '~80 min, from $290' },
                        { label: 'Trigger Point Injections', detail: '15-30 min, $150-$200' },
                        { label: 'Vitamin IM Injections', detail: '<10 min, $40-$75' },
                        { label: 'Prolotherapy Sessions', detail: '15-30 min, $150-$200' },
                    ]
                },
                {
                    name: 'Acupuncture',
                    items: [
                        { label: 'Classic Acupuncture', detail: '45-60 min, $100-$120' },
                        { label: 'New Patient Add-On', detail: '+$10 for extra 15 min' },
                        { label: 'Body Cupping', detail: '30 min, $70' },
                    ]
                },
                {
                    name: 'Facial Rejuvenation Acupuncture',
                    items: [
                        { label: 'Facial Rejuvenation Acupuncture', detail: '45-75 min, $100-$150' },
                        { label: 'Non-Needle Facial Acupuncture', detail: '30 min, $80' },
                    ]
                },
                {
                    name: 'Massage Therapy',
                    items: [
                        { label: '30 min Massage', detail: '$75' },
                        { label: '45 min Massage', detail: '$100' },
                        { label: '60 min Massage', detail: '$120' },
                        { label: '75 min Massage', detail: '$140' },
                        { label: '90 min Massage', detail: '$160' },
                        { label: 'Hot Stone Add-On', detail: '+$35' },
                        { label: 'Hydrotherapy Add-On', detail: '+$35' },
                        { label: 'Suction Cupping Add-On', detail: '+$50' },
                        { label: 'Kids Massage (12 & under)', detail: '30-60 min, $75-$110' },
                        { label: 'Prenatal/Postnatal Massage', detail: '45-90 min, $100-$160' },
                    ]
                },
                {
                    name: 'Osteopathic Manual Therapy',
                    items: [
                        { label: 'Initial Assessment', detail: '~50 min, $150' },
                        { label: 'Follow-Up Treatment', detail: '~25 min, $95' },
                        { label: 'Kids Initial (12 & under)', detail: '$90' },
                        { label: 'Kids Follow-Up (12 & under)', detail: '$75' },
                    ]
                },
                {
                    name: 'Combined Acupuncture + Massage',
                    items: [
                        { label: 'Combined Session (75 min)', detail: '$150' },
                        { label: 'Extended Combined Session (90 min)', detail: '$160' },
                    ]
                },
                {
                    name: 'Functional Testing',
                    items: [
                        { label: 'Food Sensitivity Testing', detail: 'IgG panels, from $275' },
                        { label: 'DUTCH Hormone Testing', detail: '18 hormone markers, dried urine' },
                        { label: 'Micronutrient Testing', detail: '33 vitamins & minerals' },
                        { label: 'SIBO Breath Testing', detail: 'Hydrogen & methane, $205' },
                        { label: 'GI-360 Gut Testing', detail: 'Comprehensive GI assessment' },
                        { label: 'Food Allergy Testing', detail: 'IgE antibody panels' },
                        { label: 'Pathogen Testing', detail: 'PAIRS / Cyrex Array 12' },
                        { label: 'Cardiovascular Testing', detail: '15+ cardiometabolic markers' },
                        { label: 'Autoimmunity Testing', detail: 'Antibody Array 5 screen' },
                        { label: 'Gluten Testing', detail: 'Cyrex Array 3x' },
                        { label: 'Mold Testing', detail: 'MycoTOX urine profile' },
                        { label: 'Environmental Toxin Testing', detail: 'GPL-Tox, 4 profile options' },
                    ]
                },
            ];

            function showServices() {
                hideWelcome();
                const container = document.getElementById('chatContainer');

                const userDiv = document.createElement('div');
                userDiv.className = 'message user';
                userDiv.innerHTML = '<div class="message-avatar"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg></div>'
                    + '<div class="message-body"><div class="message-content">Our Services</div></div>';
                container.appendChild(userDiv);

                const assistantDiv = document.createElement('div');
                assistantDiv.className = 'message assistant';
                let html = '<div class="message-avatar">N</div>';
                html += '<div class="message-body">';
                html += '<div class="message-content">Here are the services we offer at Nova Clinic! Tap a category to see what\\'s available.</div>';
                html += '<div class="services-list">';
                SERVICE_CATEGORIES.forEach(function(cat, idx) {
                    html += '<div class="service-category" id="svc-cat-' + idx + '">';
                    html += '<div class="category-header" onclick="toggleCategory(' + idx + ')">';
                    html += '<span>' + escapeHtml(cat.name) + '</span>';
                    html += '<span class="category-arrow">&#9654;</span>';
                    html += '</div>';
                    html += '<div class="sub-services">';
                    cat.items.forEach(function(item) {
                        html += '<button class="sub-service-btn" onclick="expandService(this, \\'' + escapeJs(item.label) + '\\')">';
                        html += escapeHtml(item.label);
                        html += '<span class="sub-detail">' + escapeHtml(item.detail) + '</span>';
                        html += '</button>';
                    });
                    html += '</div></div>';
                });
                html += '</div></div>';
                assistantDiv.innerHTML = html;
                container.appendChild(assistantDiv);
                container.scrollTop = container.scrollHeight;
            }

            function toggleCategory(idx) {
                const cat = document.getElementById('svc-cat-' + idx);
                if (!cat) return;
                const wasExpanded = cat.classList.contains('expanded');
                document.querySelectorAll('.service-category').forEach(c => c.classList.remove('expanded'));
                if (!wasExpanded) {
                    cat.classList.add('expanded');
                    setTimeout(() => cat.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 50);
                }
            }

            function expandService(btn, service) {
                btn.disabled = true;
                document.getElementById('questionInput').value = 'Tell me about ' + service;
                sendMessage();
            }

            function askQuestion(question) {
                document.getElementById('questionInput').value = question;
                sendMessage();
            }

            function handleAction(value) {
                const btn = event.currentTarget;
                const row = btn.closest('.actions-row');
                if (row) {
                    row.querySelectorAll('.action-btn').forEach(b => {
                        b.disabled = true;
                        b.style.opacity = '0.5';
                        b.style.cursor = 'default';
                    });
                }
                document.getElementById('questionInput').value = value;
                sendMessage();
            }

            async function sendMessage() {
                const input = document.getElementById('questionInput');
                const question = input.value.trim();
                if (!question) return;

                hideWelcome();

                const sendButton = document.getElementById('sendButton');
                input.disabled = true;
                sendButton.disabled = true;
                sendButton.innerHTML = '<span class="loading"></span>';

                addMessage(question, 'user');
                input.value = '';

                const typingId = addTypingIndicator();

                try {
                    const response = await fetch('/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            message: question,
                            session_id: sessionId
                        })
                    });

                    if (!response.ok) throw new Error('Failed to get response');

                    const data = await response.json();

                    lastResponse = {
                        question: question,
                        answer: data.answer,
                        citations: data.citations
                    };

                    removeTypingIndicator(typingId);

                    addMessage(
                        data.answer, 'assistant',
                        data.citations, data.confidence,
                        data.max_similarity, data.actions || []
                    );

                } catch (error) {
                    console.error('Error:', error);
                    removeTypingIndicator(typingId);
                    addMessage('Sorry, I had trouble connecting. Please try again in a moment!', 'assistant');
                } finally {
                    input.disabled = false;
                    sendButton.disabled = false;
                    sendButton.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>';
                    input.focus();
                }
            }

            function addTypingIndicator() {
                const container = document.getElementById('chatContainer');
                const messageDiv = document.createElement('div');
                messageDiv.className = 'message assistant';
                messageDiv.id = 'typing-' + Date.now();
                messageDiv.innerHTML = '<div class="message-avatar">N</div><div class="message-body"><div class="typing-indicator"><span></span><span></span><span></span></div></div>';
                container.appendChild(messageDiv);
                container.scrollTop = container.scrollHeight;
                return messageDiv.id;
            }

            function removeTypingIndicator(id) {
                const el = document.getElementById(id);
                if (el) el.remove();
            }

            function addMessage(text, sender, citations = [], confidence = null, maxSimilarity = null, actions = []) {
                const container = document.getElementById('chatContainer');
                const messageDiv = document.createElement('div');
                messageDiv.className = 'message ' + sender;

                let avatarHtml = '';
                if (sender === 'assistant') {
                    avatarHtml = '<div class="message-avatar">N</div>';
                } else {
                    avatarHtml = '<div class="message-avatar"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg></div>';
                }

                let bodyHtml = '<div class="message-body">';
                bodyHtml += '<div class="message-content">' + escapeHtml(text);


                if (citations && citations.length > 0) {
                    bodyHtml += '<div class="citations"><h4>Sources</h4>';
                    citations.forEach(function(c) {
                        bodyHtml += '<div class="citation-item"><strong>' + escapeHtml(c.section_heading) + '</strong></div>';
                    });
                    bodyHtml += '</div>';
                }

                if (sender === 'assistant') {
                    bodyHtml += '<div class="feedback-buttons">';
                    bodyHtml += '<button class="feedback-btn" onclick="submitFeedback(1, this)" title="Helpful"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 10v12"/><path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2h0a3.13 3.13 0 0 1 3 3.88Z"/></svg></button>';
                    bodyHtml += '<button class="feedback-btn" onclick="submitFeedback(-1, this)" title="Not helpful"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 14V2"/><path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22h0a3.13 3.13 0 0 1-3-3.88Z"/></svg></button>';
                    bodyHtml += '</div>';
                }

                bodyHtml += '</div>';

                if (actions && actions.length > 0 && sender === 'assistant') {
                    // Separate patient_card from regular actions
                    var patientCard = null;
                    var regularActions = [];
                    actions.forEach(function(a) {
                        if (a.action_type === 'patient_card') {
                            try { patientCard = JSON.parse(a.value); } catch(e) {}
                        } else {
                            regularActions.push(a);
                        }
                    });

                    // Render patient profile card if present
                    if (patientCard) {
                        var initials = (patientCard.name || '').split(' ').map(function(n) { return n[0]; }).join('');
                        bodyHtml += '<div class="patient-card">';
                        bodyHtml += '<div class="patient-card-header">';
                        bodyHtml += '<div class="patient-avatar">' + escapeHtml(initials) + '</div>';
                        bodyHtml += '<div class="patient-header-text">';
                        bodyHtml += '<div class="patient-name">' + escapeHtml(patientCard.name || '') + '</div>';
                        bodyHtml += '<div class="patient-badge"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> Verified Patient</div>';
                        bodyHtml += '</div></div>';
                        bodyHtml += '<div class="patient-info-grid">';
                        bodyHtml += '<div class="patient-info-item"><div class="info-label">Last Visit</div><div class="info-value">' + escapeHtml(patientCard.last_visit || 'N/A') + '</div></div>';
                        if (patientCard.upcoming_appointment) {
                            bodyHtml += '<div class="patient-info-item"><div class="info-label">Upcoming</div><div class="info-value highlight">' + escapeHtml(patientCard.upcoming_appointment) + '</div></div>';
                        } else {
                            bodyHtml += '<div class="patient-info-item"><div class="info-label">Upcoming</div><div class="info-value" style="color:var(--gray-400)">None scheduled</div></div>';
                        }
                        bodyHtml += '<div class="patient-info-item"><div class="info-label">Total Visits</div><div class="info-value">' + escapeHtml(String(patientCard.total_visits || 0)) + '</div></div>';
                        bodyHtml += '<div class="patient-info-item"><div class="info-label">Preferred Practitioner</div><div class="info-value highlight">' + escapeHtml(patientCard.preferred_practitioner || 'None') + '</div></div>';
                        bodyHtml += '</div></div>';
                    }

                    // Render regular action buttons
                    if (regularActions.length > 0) {
                        bodyHtml += '<div class="actions-row">';
                        regularActions.forEach(function(a) {
                            let cls = 'quick_reply';
                            if (a.action_type === 'booking') cls = 'booking';
                            else if (a.action_type === 'back') cls = 'back';
                            bodyHtml += '<button class="action-btn ' + cls + '" onclick="handleAction(\\'' + escapeJs(a.value) + '\\')">'
                                + escapeHtml(a.label) + '</button>';
                        });
                        bodyHtml += '</div>';
                    }
                }

                bodyHtml += '</div>';

                messageDiv.innerHTML = avatarHtml + bodyHtml;
                container.appendChild(messageDiv);
                container.scrollTop = container.scrollHeight;
            }

            async function submitFeedback(rating, button) {
                if (!lastResponse) return;
                const buttons = button.parentElement.querySelectorAll('.feedback-btn');
                buttons.forEach(function(btn) { btn.disabled = true; });
                button.classList.add(rating > 0 ? 'active-up' : 'active-down');

                try {
                    await fetch('/feedback', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            session_id: sessionId,
                            question: lastResponse.question,
                            answer: lastResponse.answer,
                            citations: lastResponse.citations,
                            rating: rating
                        })
                    });
                } catch (error) {
                    console.error('Error submitting feedback:', error);
                }
            }

            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }

            function escapeJs(text) {
                return text.replace(/\\\\/g, '\\\\\\\\').replace(/'/g, "\\\\'");
            }

            document.getElementById('questionInput').focus();
        </script>
    </body>
    </html>
    """
    return html_content
