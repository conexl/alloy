package services

import (
	"math"
	"regexp"
	"strconv"
	"strings"

	"communication-service/internal/domain"

	"github.com/sirupsen/logrus"
)

type QuoteParser struct {
	logger *logrus.Logger

	// Regex patterns
	pricePattern   *regexp.Regexp
	daysPattern    *regexp.Regexp
	weeksPattern   *regexp.Regexp
	addressPattern *regexp.Regexp
}

func NewQuoteParser(logger *logrus.Logger) *QuoteParser {
	return &QuoteParser{
		logger:         logger,
		pricePattern:   regexp.MustCompile(`(?i)(?:цена|стоимость|price|cost|руб|rub|₽)[^\d]{0,30}(\d[\d\s]*(?:[.,]\d{1,2})?)|(\d[\d\s]*(?:[.,]\d{1,2})?)\s*(?:руб|rub|₽|р\.)|(?:^|[^\d])(\d{1,3}(?:\s?\d{3})*(?:[.,]\d{2})?)\s*(?:за единицу|за шт|/шт|/ед\b)`),
		daysPattern:    regexp.MustCompile(`(?i)(?:срок|поставк|delivery|lead\.?time)[^\d]{0,15}(\d+)\s*(?:рабочих\s+)?(?:дн|day)`),
		weeksPattern:   regexp.MustCompile(`(?i)(\d+)\s*(?:недел|week)`),
		addressPattern: regexp.MustCompile(`(?i)(?:самовывоз|склад|отгрузк|pickup|from)[^\n]{0,5}[:\s](.{10,100}?)(?:\n|$|\.(?:\s|$))`),
	}
}

func (p *QuoteParser) Parse(text string, item *domain.Item) *domain.ParsedQuote {
	// Normalize text
	text = strings.ToLower(text)
	text = strings.ReplaceAll(text, "\n", " ")
	text = strings.ReplaceAll(text, "\r", " ")

	price := p.parsePrice(text)
	if price == nil {
		return nil
	}

	deliveryDays := p.parseDeliveryDays(text)
	if deliveryDays == nil {
		// Price without delivery days is acceptable
		deliveryDays = new(int)
		*deliveryDays = 0
	}

	pickupAddress := p.parsePickupAddress(text)

	confidence := p.calculateConfidence(text, price, deliveryDays)

	return &domain.ParsedQuote{
		Price:         *price,
		DeliveryDays:  *deliveryDays,
		PickupAddress: pickupAddress,
		Confidence:    confidence,
	}
}

func (p *QuoteParser) parsePrice(text string) *float64 {
	matches := p.pricePattern.FindAllStringSubmatch(text, -1)
	if len(matches) == 0 {
		return nil
	}

	var prices []float64
	for _, match := range matches {
		var priceStr string
		if match[1] != "" {
			priceStr = match[1]
		} else if match[2] != "" {
			priceStr = match[2]
		} else {
			continue
		}

		// Normalize number
		priceStr = strings.ReplaceAll(priceStr, " ", "")
		priceStr = strings.ReplaceAll(priceStr, ",", ".")

		price, err := strconv.ParseFloat(priceStr, 64)
		if err != nil {
			continue
		}

		// Filter obvious errors
		if price >= 1 && price <= 100_000_000 {
			prices = append(prices, price)
		}
	}

	if len(prices) == 0 {
		return nil
	}

	// Take the smallest price (suppliers often list both with/without VAT)
	minPrice := prices[0]
	for _, p := range prices[1:] {
		if p < minPrice {
			minPrice = p
		}
	}

	return &minPrice
}

func (p *QuoteParser) parseDeliveryDays(text string) *int {
	// Check for weeks first
	if matches := p.weeksPattern.FindStringSubmatch(text); len(matches) > 1 {
		weeks, err := strconv.Atoi(matches[1])
		if err == nil && weeks > 0 && weeks < 52 {
			days := weeks * 7
			return &days
		}
	}

	// Check for days
	if matches := p.daysPattern.FindStringSubmatch(text); len(matches) > 1 {
		days, err := strconv.Atoi(matches[1])
		if err == nil && days > 0 && days <= 730 {
			// Check if it's working days (рабочих)
			// Find the match position in original text to check context
			matchIdx := p.daysPattern.FindStringIndex(text)
			if matchIdx != nil && matchIdx[0] > 0 {
				// Look back up to 20 characters for "рабочих"
				start := max(0, matchIdx[0]-20)
				context := text[start:matchIdx[0]]
				if strings.Contains(context, "рабочих") {
					// Convert working days to calendar days (~1.4x)
					days = int(math.Ceil(float64(days) * 1.4))
				}
			}
			return &days
		}
	}

	return nil
}

func (p *QuoteParser) parsePickupAddress(text string) *string {
	if matches := p.addressPattern.FindStringSubmatch(text); len(matches) > 1 {
		address := strings.TrimSpace(matches[1])
		if len(address) > 10 && len(address) < 200 {
			return &address
		}
	}
	return nil
}

func (p *QuoteParser) calculateConfidence(text string, price *float64, days *int) float64 {
	confidence := 0.5 // Base confidence

	if price != nil {
		confidence += 0.3
	}
	if days != nil && *days > 0 {
		confidence += 0.2
	}

	// Check for explicit quote indicators
	lowerText := strings.ToLower(text)
	if strings.Contains(lowerText, "кп") || strings.Contains(lowerText, "коммерческое предложение") {
		confidence += 0.2
	}
	if strings.Contains(lowerText, "стоимость") || strings.Contains(lowerText, "цена") {
		confidence += 0.1
	}
	if strings.Contains(lowerText, "срок") {
		confidence += 0.1
	}

	if confidence > 1.0 {
		confidence = 1.0
	}

	return confidence
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}
