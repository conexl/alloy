package services

import (
	"bytes"
	"fmt"
	"html/template"

	"communication-service/internal/domain"

	"github.com/sirupsen/logrus"
)

type TemplateService struct {
	logger  *logrus.Logger
	htmlTpl *template.Template
	textTpl *template.Template
}

func NewTemplateService(logger *logrus.Logger) *TemplateService {
	// HTML template
	htmlTpl := template.Must(template.New("rfq").Parse(`
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
body { font-family: Arial, sans-serif; line-height: 1.6; }
.container { max-width: 600px; margin: 0 auto; }
.header { background-color: #f4f4f4; padding: 20px; text-align: center; }
.content { padding: 20px; }
.table { width: 100%; border-collapse: collapse; margin: 20px 0; }
.table td { padding: 10px; border: 1px solid #ddd; }
.table td:first-child { font-weight: bold; width: 40%; background-color: #f9f9f9; }
.profile-block { background-color: #e8f5e9; padding: 15px; border-radius: 5px; margin: 20px 0; }
.profile-block h3 { margin-top: 0; color: #2e7d32; }
.footer { font-size: 12px; color: #666; margin-top: 30px; padding-top: 10px; border-top: 1px solid #eee; }
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h2>Запрос коммерческого предложения #RFQ-{{.RFQID}}-{{.ItemID}}</h2>
    </div>
    <div class="content">
        <p>Уважаемые коллеги,</p>

        <p>Просим предоставить коммерческое предложение на следующую позицию:</p>

        <table class="table">
            <tr><td>Наименование</td><td>{{.ItemName}}</td></tr>
            <tr><td>Техобозначение</td><td>{{.TechCode}}</td></tr>
            <tr><td>ГОСТ/ТУ</td><td>{{.GOST}}</td></tr>
            <tr><td>Единица измерения</td><td>{{.Unit}}</td></tr>
            <tr><td>Количество</td><td>{{.Qty}}</td></tr>
            <tr><td>Срок поставки</td><td>{{.Deadline}}</td></tr>
            <tr><td>Город получения</td><td>{{.Location}}</td></tr>
            <tr><td>Условия оплаты</td><td>{{.PaymentTerms}}</td></tr>
        </table>

        <p>Просим указать в ответе:</p>
        <ul>
            <li>Цену без НДС за единицу</li>
            <li>Срок поставки (в днях)</li>
            <li>Адрес самовывоза</li>
        </ul>

        {{if .HasProfile}}
        <div class="profile-block">
            <h3>Реквизиты заказчика</h3>
            <table class="table">
                {{if .CompanyName}}<tr><td>Организация</td><td>{{.CompanyName}}</td></tr>{{end}}
                {{if .Inn}}<tr><td>ИНН</td><td>{{.Inn}}</td></tr>{{end}}
                {{if .Kpp}}<tr><td>КПП</td><td>{{.Kpp}}</td></tr>{{end}}
                {{if .Address}}<tr><td>Адрес</td><td>{{.Address}}</td></tr>{{end}}
                {{if .Phone}}<tr><td>Телефон</td><td>{{.Phone}}</td></tr>{{end}}
                {{if .ContactPerson}}<tr><td>Контактное лицо</td><td>{{.ContactPerson}}</td></tr>{{end}}
            </table>
        </div>
        {{end}}

        <p>С уважением,<br>{{if .CompanyName}}{{.CompanyName}}{{else}}Отдел закупок{{end}}</p>
    </div>
    <div class="footer">
        <p>Это автоматическое сообщение, пожалуйста, не отвечайте на него напрямую.<br>
        Для ответа используйте кнопку "Ответить" в вашем почтовом клиенте.</p>
    </div>
</div>
</body>
</html>
`))

	// Plain text template
	textTpl := template.Must(template.New("rfq_text").Parse(`
Запрос коммерческого предложения #RFQ-{{.RFQID}}-{{.ItemID}}

Уважаемые коллеги,

Просим предоставить коммерческое предложение на следующую позицию:

Наименование:        {{.ItemName}}
Техобозначение:      {{.TechCode}}
ГОСТ/ТУ:             {{.GOST}}
Единица измерения:   {{.Unit}}
Количество:          {{.Qty}}
Срок поставки:       {{.Deadline}}
Город получения:     {{.Location}}
Условия оплаты:      {{.PaymentTerms}}

Просим указать в ответе:
- Цену без НДС за единицу
- Срок поставки (в днях)
- Адрес самовывоза
{{if .HasProfile}}
Реквизиты заказчика:
{{if .CompanyName}}  Организация:         {{.CompanyName}}{{end}}
{{if .Inn}}  ИНН:                  {{.Inn}}{{end}}
{{if .Kpp}}  КПП:                  {{.Kpp}}{{end}}
{{if .Address}}  Адрес:                {{.Address}}{{end}}
{{if .Phone}}  Телефон:              {{.Phone}}{{end}}
{{if .ContactPerson}}  Контактное лицо:      {{.ContactPerson}}{{end}}
{{end}}
С уважением,
{{if .CompanyName}}{{.CompanyName}}{{else}}Отдел закупок{{end}}

----
Это автоматическое сообщение, пожалуйста, не отвечайте на него напрямую.
Для ответа используйте кнопку "Ответить" в вашем почтовом клиенте.
`))

	return &TemplateService{
		logger:  logger,
		htmlTpl: htmlTpl,
		textTpl: textTpl,
	}
}

type RFQTemplateData struct {
	RFQID        int64
	ItemID       int64
	ItemName     string
	TechCode     string
	GOST         string
	Unit         string
	Qty          float64
	Deadline     string
	Location     string
	PaymentTerms string
	HasProfile   bool
	CompanyName  string
	Inn          string
	Kpp          string
	Address      string
	Phone        string
	Email        string
	ContactPerson string
}

func (s *TemplateService) RenderRFQ(item *domain.Item, rfq *domain.RFQRequest, profile *domain.UserProfile) (string, string, error) {
	data := RFQTemplateData{
		RFQID:        rfq.ID,
		ItemID:       item.ID,
		ItemName:     item.Name,
		TechCode:     item.TechCode,
		GOST:         item.GOST,
		Unit:         item.Unit,
		Qty:          item.Qty,
		Deadline:     item.Deadline.Format("02.01.2006"),
		Location:     item.Location,
		PaymentTerms: item.PaymentTerms,
	}

	if profile != nil {
		data.HasProfile = true
		data.CompanyName = profile.CompanyName
		data.Inn = profile.Inn
		data.Kpp = profile.Kpp
		data.Address = profile.Address
		data.Phone = profile.Phone
		data.Email = profile.Email
		data.ContactPerson = profile.ContactPerson
	}

	// Render HTML
	var htmlBuf bytes.Buffer
	if err := s.htmlTpl.Execute(&htmlBuf, data); err != nil {
		return "", "", fmt.Errorf("failed to render HTML template: %w", err)
	}

	// Render text
	var textBuf bytes.Buffer
	if err := s.textTpl.Execute(&textBuf, data); err != nil {
		return "", "", fmt.Errorf("failed to render text template: %w", err)
	}

	return htmlBuf.String(), textBuf.String(), nil
}

func (s *TemplateService) GetSubject(item *domain.Item, rfq *domain.RFQRequest, profile *domain.UserProfile) string {
	prefix := ""
	if profile != nil && profile.CompanyName != "" {
		prefix = "[" + profile.CompanyName + "] "
	}
	return fmt.Sprintf("%sЗапрос коммерческого предложения #RFQ-%d-%d | %s",
		prefix, rfq.ID, item.ID, item.Name)
}
