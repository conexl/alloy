## Goal
- Build a full-featured VK Mini App web interface for RFQ management with real-time updates and a modern dark glassmorphism UI, alongside the existing email-based quote processing system

## Constraints & Preferences
- VK Mini App must use auto-auth via VK Bridge (`vk1.a.Z557BxTK...` token, group_id `238402953`)
- Fallback mode for browser dev: `?vk_user_id=1061591442` bypasses VK Bridge
- SSE (Server-Sent Events) for real-time quote notifications — not WebSockets
- Dark theme with glassmorphism, gradients, and glow effects (inspired by animejs.com)
- Excel (.xlsx) upload for RFQ creation
- Email/RFQ backend must continue working in parallel
- Framer Motion for all UI animations (spring physics, stagger, layout animations)

## Progress
### Done
- **Critical bug fixed**: `ai_result` JSONB field received plain strings → `MarkEmailsProcessed` silently failed, emails stuck in `pending`. Fixed with `json.Marshal` and error handling
- **All 33 pending emails processed**: 33/33 marked `done`, 15 quotes extracted, 4 `manual_review` (visit_site), 0 errors
- **AI prompt improvements**: better `visit_site` detection, new `unavailable` action, added to `BatchAnalysisResult`/`EmailAnalysisResult`
- **Migration `007_add_unavailable_status.up.sql`**: added `unavailable` to `orphan_emails` status check
- **VK keys updated**: `.env` and `vk-bot/.env` token + group_id changed to `238402953`
- **VK Mini App frontend** (`vk-mini-app/`): React + Vite + TypeScript + Tailwind CSS + Framer Motion + Lucide icons + `react-router-dom`
- **Animation system**: `/src/animations/index.tsx` — spring configs, `PageTransition`, `AnimatedCard`, `AnimatedList`, `AnimatedNumber`, `LayoutAnimation`, stagger variants
- **App-level animations**: `AnimatePresence` page transitions, loading spinner rotation, SSE alert bounce, error state spring scale
- **Custom UI components**: `Card` (glassmorphism + glow), `Button` (gradient variant), `Badge`, `Sidebar`, `MobileNav`, `Layout`
- **Pages**: Dashboard (stats cards + gradient accents), RFQ List (search + filter), RFQ Detail (progress bar + positions), Item Detail (quotes/suppliers/threads tabs + best price highlight + winner selection), Profile (company form), Create RFQ (drag-drop Excel upload)
- **Winner selection UI fully implemented**:
  - Backend: `POST /api/items/{item_id}/winner` with upsert logic, margin_pct support
  - Frontend: `api.selectWinner()` method, golden winner card with crown icon, best price highlight, inline margin input form, "Выбрать победителя" button per quote
  - Smooth animations: spring scale for winner reveal, AnimatePresence for best price ↔ winner transition
- **Web App Backend** (`web-app-backend/`): FastAPI on port 8002 with SSE endpoint `/api/sse/subscribe`, Redis Stream listener for `quote_received`
- **API endpoints**: `GET /api/rfqs`, `GET /api/rfqs/{id}/items`, `GET /api/items/{id}` (includes `winner`), `GET /api/items/{id}/quotes`, `GET /api/items/{id}/suppliers`, `GET /api/items/{id}/threads`, `POST /api/rfqs` (multipart Excel upload), `POST /api/items/{item_id}/winner` (upsert), `GET /api/profile`, `PATCH /api/profile`
- **SSE client**: auto-reconnect with exponential backoff, quote received alerts with "Посмотреть" button
- **VK Bot updated**: simplified status (last RFQ only), added "📱 Открыть приложение" button linking to Mini App
- **Docker Compose**: added `vk-mini-app` (port 3000) and `web-app-backend` (port 8002) services
- **Build verified**: Mini App serves on `localhost:3000`, API on `localhost:8002`, CSS 50.55KB, JS 383.22KB

### In Progress
- (none)

### Blocked
- (none)

## Key Decisions
- Switch from VKUI to custom Tailwind CSS dark theme because user found VKUI "не адаптированный" and wanted something closer to animejs.com's aesthetic
- Use **glassmorphism** (`backdrop-filter: blur`, semi-transparent backgrounds, white borders at 5-10% opacity) instead of solid cards
- Use **gradient accents** (indigo → purple → pink) for stats cards, badges, and buttons instead of flat colors
- Use **EventSource/SSE** instead of WebSockets for real-time updates — simpler for one-way server→client notifications
- VK Bridge gets 3-second timeout; falls back to URL query param `vk_user_id` if not inside VK iframe
- `AIBatchWorker` uses `json.Marshal` for `ai_result` to satisfy JSONB column type
- `.ts` → `.tsx` rename required for files containing JSX (animations component)
- Winner selection uses **upsert** (`ON CONFLICT (item_id) DO UPDATE`) — allows re-selecting winner if needed

## Next Steps
- Deploy Mini App publicly and register it in VK community settings with iframe URL
- Add manual reply to supplier threads from web app
- Add dark/light theme toggle if requested

## Critical Context
- **VK Mini App URL for bot button**: `https://vk.com/app238402953`
- **Local dev URL**: `http://localhost:3000?vk_user_id=1061591442`
- **API base**: `http://localhost:8002`
- **All services running**: `vk-mini-app` (3000), `web-app-backend` (8002), `vk-bot`, `communication-service` (8080), `report-service` (8081), `supplier-finder` (8000), `tender-postgres`, `tender-redis`
- **Build sizes**: CSS 50.55KB, JS 383.22KB
- **Processing stats**: 15% quote extraction rate, 12% visit_site, 73% questions/ignored, 15 quotes from 33 emails
- **Winner DB schema**: `winners(id, item_id UNIQUE, quote_id, final_price, margin_pct, chosen_at)` — upsert on `item_id`

## Relevant Files
- `/home/conexl/Code/Project/vk-mini-app/src/animations/index.tsx`: reusable Framer Motion components (springs, page transitions, stagger lists)
- `/home/conexl/Code/Project/vk-mini-app/src/App.tsx`: AnimatePresence routes, animated loading/error states, SSE alert
- `/home/conexl/Code/Project/vk-mini-app/src/index.css`: glassmorphism, gradient animations, custom scrollbar
- `/home/conexl/Code/Project/vk-mini-app/src/components/Card.tsx`: glass card with glow effect
- `/home/conexl/Code/Project/vk-mini-app/src/components/Sidebar.tsx`: glass sidebar with gradient nav items
- `/home/conexl/Code/Project/vk-mini-app/src/hooks/useVK.ts`: VK Bridge init with 3s timeout + fallback
- `/home/conexl/Code/Project/vk-mini-app/src/api/client.ts`: Axios + SSE EventSource subscriber + `selectWinner` method
- `/home/conexl/Code/Project/vk-mini-app/src/pages/ItemDetail.tsx`: quotes/suppliers/threads tabs — winner card, best price highlight, margin input form
- `/home/conexl/Code/Project/vk-mini-app/src/types/index.ts`: TypeScript interfaces (Item with `winner?: Winner`, Winner, Quote, etc.)
- `/home/conexl/Code/Project/web-app-backend/cmd/main.py`: FastAPI with SSE, Excel parser, `POST /api/items/{item_id}/winner` endpoint
- `/home/conexl/Code/Project/web-app-backend/Dockerfile`: includes `python-multipart`, `openpyxl`, `redis`
- `/home/conexl/Code/Project/vk-bot/internal/keyboards/keyboards.py`: Mini App URL constant + OpenLink button
- `/home/conexl/Code/Project/docker-compose.yml`: `vk-mini-app` and `web-app-backend` services added
- `/home/conexl/Code/Project/communication-service/internal/workers/ai_batch_worker.go`: fixed `json.Marshal` for `ai_result`
- `/home/conexl/Code/Project/communication-service/internal/services/openrouter_client.go`: updated prompts with `unavailable` and `visit_site` examples
- `/home/conexl/Code/Project/migrations/003_quotes_winners.sql`: `winners` table schema
