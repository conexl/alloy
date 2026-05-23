package services

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"communication-service/internal/config"
	"communication-service/internal/domain"

	"github.com/sirupsen/logrus"
)

type OpenRouterClient struct {
	apiKey string
	config *config.Config
	logger *logrus.Logger
	client *http.Client
}

func NewOpenRouterClient(config *config.Config, logger *logrus.Logger) *OpenRouterClient {
	return &OpenRouterClient{
		apiKey: config.OpenRouterAPIKey,
		config: config,
		logger: logger,
		client: &http.Client{
			Timeout: 300 * time.Second,
		},
	}
}

type ChatMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type ChatCompletionRequest struct {
	Model     string        `json:"model"`
	MaxTokens int           `json:"max_tokens"`
	Messages  []ChatMessage `json:"messages"`
}

type ChatCompletionResponse struct {
	Choices []struct {
		Message struct {
			Content string `json:"content"`
		} `json:"message"`
	} `json:"choices"`
	Error *struct {
		Message string `json:"message"`
	} `json:"error"`
}

type EmailAnalysisRequest struct {
	Body string
	Item *domain.Item
	RFQ  *domain.RFQRequest
}

type EmailAnalysisResult struct {
	Action        string   `json:"action"`
	Price         *float64 `json:"price,omitempty"`
	DeliveryDays  *int     `json:"delivery_days,omitempty"`
	PickupAddress *string  `json:"pickup_address,omitempty"`
	Reply         string   `json:"reply,omitempty"`
	SiteURL       *string  `json:"site_url,omitempty"`
	Unavailable   bool     `json:"unavailable,omitempty"`
}

func (c *OpenRouterClient) AnalyzeEmail(ctx context.Context, req *EmailAnalysisRequest) (*EmailAnalysisResult, error) {
	if c.apiKey == "" {
		return c.fallbackParse(req), nil
	}

	systemPrompt := `Ты — менеджер по закупкам. Извлекай цены из ответов поставщиков.

Если в ответе есть хотя бы одно число, похожее на цену (рубли, USD, EUR), или слова "цена", "стоимость", "руб", "price" — верни JSON с action="quote". Укажи:
- price: число (целое или дробное), извлеки цену из текста
- delivery_days: число (дни поставки) или 0 если не указано
- pickup_address: строка (адрес самовывоза) или "" если нет

Если поставщик задал вопрос, запросил уточнение — верни JSON с action="question" и reply (твой ответ, кратко, по-русски).

Если поставщик пишет "цена на сайте", "смотрите на сайте", "актуальная цена на сайте", "обратитесь к дилерам" — верни JSON с action="visit_site" и site_url (URL если есть).

Если поставщик отвечает что товара нет, не поставляют, не производят, не имеют в ассортименте — верни JSON с action="unavailable" и unavailable=true.

ВАЖНО: 
- Если в тексте есть любое упоминание цены или стоимости — это КОТИРОВКА (quote)
- Если товара нет у поставщика — это unavailable, не question

ПРИМЕРЫ КОТИРОВОК (action="quote"):
- "стоимость 1 850 руб."
- "цена 5000р с НДС"
- "1250,50 рублей"
- "могу предложить 3200 руб за штуку"

ПРИМЕРЫ visit_site (action="visit_site"):
- "цена на сайте актуальная"
- "обратитесь к дилерам РФ"
- "смотрите на нашем сайте"

ПРИМЕРЫ unavailable (action="unavailable"):
- "К сожалению с таким помочь не сможем"
- "Данного товара нет по наличию, не поставляем"
- "не сталкивались с таким магнитом, не знаем"
- "данный товар отсутствует в нашем ассортименте"

ПРИМЕРЫ ВОПРОСОВ (action="question"):
- "какой у вас ИНН?"
- "нужна более точная информация по тех. характеристикам"
- "с НДС или без?"

Отвечай ТОЛЬКО JSON, без пояснений. Примеры:
{"action":"quote","price":18500,"delivery_days":14,"pickup_address":"г. Москва"}
{"action":"question","reply":"Уточните, пожалуйста, цену с НДС или без?"}
{"action":"visit_site","site_url":"https://example.com/product"}
{"action":"unavailable","unavailable":true}`

	userPrompt := fmt.Sprintf(`Позиция: %s
Техобозначение: %s
ГОСТ/ТУ: %s
Количество: %.2f %s
Срок поставки: до %s
Город получения: %s
Условия оплаты: %s

Ответ поставщика:
%s`,
		req.Item.Name,
		req.Item.TechCode,
		req.Item.GOST,
		req.Item.Qty,
		req.Item.Unit,
		req.Item.Deadline.Format("02.01.2006"),
		req.Item.Location,
		req.Item.PaymentTerms,
		req.Body,
	)

	chatReq := ChatCompletionRequest{
		Model:     c.config.OpenRouterModel,
		MaxTokens: 500,
		Messages: []ChatMessage{
			{Role: "system", Content: systemPrompt},
			{Role: "user", Content: userPrompt},
		},
	}

	jsonData, err := json.Marshal(chatReq)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal request: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", "https://openrouter.ai/api/v1/chat/completions", bytes.NewBuffer(jsonData))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Authorization", "Bearer "+c.apiKey)
	httpReq.Header.Set("X-Application-Name", "Tender-Communication-Service")

	resp, err := c.client.Do(httpReq)
	if err != nil {
		c.logger.WithError(err).Error("OpenRouter API request failed")
		return c.fallbackParse(req), nil
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		c.logger.WithFields(logrus.Fields{
			"status": resp.StatusCode,
			"body":   string(body),
		}).Error("OpenRouter API error")
		return c.fallbackParse(req), nil
	}

	var chatResp ChatCompletionResponse
	if err := json.Unmarshal(body, &chatResp); err != nil {
		return nil, fmt.Errorf("failed to unmarshal response: %w", err)
	}

	if chatResp.Error != nil {
		return nil, fmt.Errorf("OpenRouter API error: %s", chatResp.Error.Message)
	}

	if len(chatResp.Choices) == 0 {
		return nil, fmt.Errorf("no content in response")
	}

	content := chatResp.Choices[0].Message.Content

	var result EmailAnalysisResult
	if err := json.Unmarshal([]byte(content), &result); err != nil {
		return &EmailAnalysisResult{
			Action: "question",
			Reply:  content,
		}, nil
	}

	if result.Action == "" {
		result.Action = "question"
	}

	return &result, nil
}

type BatchEmailRequest struct {
	Index         int
	Body          string
	Subject       string
	Item          *domain.Item
	RFQ           *domain.RFQRequest
	ThreadHistory []domain.ThreadMessage
	QuoteHistory  []domain.QuoteHistory
	SupplierID    int64
	SupplierEmail string
}

type BatchAnalysisResult struct {
	Index         int                `json:"index"`
	Action        string             `json:"action"`
	Price         *float64           `json:"price,omitempty"`
	DeliveryDays  *int               `json:"delivery_days,omitempty"`
	PickupAddress *string            `json:"pickup_address,omitempty"`
	Reply         string             `json:"reply,omitempty"`
	SiteURL       *string            `json:"site_url,omitempty"`
	Unavailable   bool               `json:"unavailable,omitempty"`
}

func (c *OpenRouterClient) AnalyzeEmailBatch(ctx context.Context, requests []BatchEmailRequest) ([]BatchAnalysisResult, error) {
	if c.apiKey == "" {
		return c.fallbackBatchParse(requests), nil
	}

	if len(requests) == 0 {
		return nil, nil
	}

	var promptParts []string

	// Include thread history from the first request (assuming same supplier)
	if len(requests[0].ThreadHistory) > 0 {
		promptParts = append(promptParts, "История переписки с поставщиком:")
		for _, m := range requests[0].ThreadHistory {
			direction := "Поставщик"
			if m.Direction == "outbound" {
				direction = "Мы"
			}
			promptParts = append(promptParts, fmt.Sprintf("[%s]: %s", direction, m.Body))
		}
		promptParts = append(promptParts, "")
	}

	// Include quote history from the first request (assuming same supplier)
	if len(requests[0].QuoteHistory) > 0 {
		promptParts = append(promptParts, "История котировок от этого поставщика (возможно с других email):")
		for _, q := range requests[0].QuoteHistory {
			promptParts = append(promptParts, fmt.Sprintf("- %s: %.2f руб., %d дней, %s",
				q.ItemName, q.Price, q.DeliveryDays, q.PickupAddress))
		}
		promptParts = append(promptParts, "")
	}

	promptParts = append(promptParts, "Новые письма для анализа:")
	for _, req := range requests {
		promptParts = append(promptParts, fmt.Sprintf("=== Письмо %d ===", req.Index))
		promptParts = append(promptParts, fmt.Sprintf("Тема: %s", req.Subject))
		if req.Item != nil {
			promptParts = append(promptParts, fmt.Sprintf("Позиция: %s | Техобозначение: %s | ГОСТ/ТУ: %s | Количество: %.2f %s | Срок: до %s | Город: %s | Оплата: %s",
				req.Item.Name, req.Item.TechCode, req.Item.GOST, req.Item.Qty, req.Item.Unit,
				req.Item.Deadline.Format("02.01.2006"), req.Item.Location, req.Item.PaymentTerms))
		}
		promptParts = append(promptParts, fmt.Sprintf("Тело письма:\n%s", req.Body))
		promptParts = append(promptParts, "")
	}

	systemPrompt := `Ты — менеджер по закупкам. Тебе прислали несколько писем от одного поставщика. Проанализируй КАЖДОЕ письмо отдельно.

	Для каждого письма определи:
- action: "quote" если есть цена/котировка, "question" если вопрос/уточнение, "visit_site" если цена только на сайте, "unavailable" если товара нет/не поставляют
- price: число (цена за единицу) или null
- delivery_days: число дней поставки или null
- pickup_address: адрес самовывоза или ""
- reply: ответ на вопрос (только если action="question")
- site_url: URL сайта (только если action="visit_site")
- unavailable: true (только если action="unavailable")

ВАЖНО: 
- Если в письме есть хотя бы одно упоминание цены — это КОТИРОВКА (action="quote")
- Если поставщик пишет "цена на сайте", "смотрите на сайте", "актуальная цена на сайте", "обратитесь к дилерам" — это visit_site, извлеки URL
- Если поставщик пишет "нет в наличии", "не поставляем", "не производим", "не имеем в ассортименте" — это unavailable
- Анализируй письма НЕЗАВИСИМО друг от друга, даже если они по разным позициям
- Если письмо содержит цену на несколько позиций — укажи цену для основной позиции из контекста
- Если письмо содержит "КП во вложении" но вложение не распарсено — попробуй найти цену в теле, если нет — это question с reply="Просьба прислать цены в теле письма"

Примеры:
{"index":1,"action":"quote","price":18500,"delivery_days":14,"pickup_address":"г. Москва","reply":"","site_url":null,"unavailable":false}
{"index":2,"action":"question","price":null,"delivery_days":null,"pickup_address":"","reply":"Уточните, пожалуйста, срок поставки","site_url":null,"unavailable":false}
{"index":3,"action":"visit_site","price":null,"delivery_days":null,"pickup_address":"","reply":"","site_url":"https://example.com/product","unavailable":false}
{"index":4,"action":"unavailable","price":null,"delivery_days":null,"pickup_address":"","reply":"","site_url":null,"unavailable":true}

Ответь ТОЛЬКО JSON массивом, без пояснений:`

	chatReq := ChatCompletionRequest{
		Model:     c.config.OpenRouterModel,
		MaxTokens: 1000 + len(requests)*200,
		Messages: []ChatMessage{
			{Role: "system", Content: systemPrompt},
			{Role: "user", Content: strings.Join(promptParts, "\n")},
		},
	}

	jsonData, err := json.Marshal(chatReq)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal batch request: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", "https://openrouter.ai/api/v1/chat/completions", bytes.NewBuffer(jsonData))
	if err != nil {
		return nil, fmt.Errorf("failed to create batch request: %w", err)
	}

	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Authorization", "Bearer "+c.apiKey)
	httpReq.Header.Set("X-Application-Name", "Tender-Communication-Service")

	resp, err := c.client.Do(httpReq)
	if err != nil {
		c.logger.WithError(err).Error("OpenRouter batch API request failed")
		return c.fallbackBatchParse(requests), nil
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read batch response: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		c.logger.WithFields(logrus.Fields{
			"status": resp.StatusCode,
			"body":   string(body),
		}).Error("OpenRouter batch API error")
		return c.fallbackBatchParse(requests), nil
	}

	var chatResp ChatCompletionResponse
	if err := json.Unmarshal(body, &chatResp); err != nil {
		return nil, fmt.Errorf("failed to unmarshal batch response: %w", err)
	}

	if chatResp.Error != nil {
		return nil, fmt.Errorf("OpenRouter batch API error: %s", chatResp.Error.Message)
	}

	if len(chatResp.Choices) == 0 {
		return nil, fmt.Errorf("no content in batch response")
	}

	content := chatResp.Choices[0].Message.Content

	// Try to extract JSON array from content
	content = c.extractJSONArray(content)

	var results []BatchAnalysisResult
	if err := json.Unmarshal([]byte(content), &results); err != nil {
		c.logger.WithError(err).WithField("content", content).Warn("Failed to parse batch JSON, using fallback")
		return c.fallbackBatchParse(requests), nil
	}

	return results, nil
}

func (c *OpenRouterClient) extractJSONArray(content string) string {
	// Find first '[' and last ']'
	start := strings.Index(content, "[")
	end := strings.LastIndex(content, "]")
	if start != -1 && end != -1 && start < end {
		return content[start : end+1]
	}
	return content
}

func (c *OpenRouterClient) fallbackBatchParse(requests []BatchEmailRequest) []BatchAnalysisResult {
	results := make([]BatchAnalysisResult, len(requests))
	for i, req := range requests {
		results[i] = BatchAnalysisResult{
			Index:  req.Index,
			Action: "question",
			Reply:  "Получил ваш ответ. Уточню у коллег и вернусь с ответом.",
		}
	}
	return results
}

func (c *OpenRouterClient) fallbackParse(req *EmailAnalysisRequest) *EmailAnalysisResult {
	return &EmailAnalysisResult{
		Action: "question",
		Reply:  "Получил ваш ответ. Уточню у коллег и вернусь с ответом.",
	}
}
