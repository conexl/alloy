package domain

import (
	"time"
)

// Item represents a position from database
type Item struct {
	ID           int64     `db:"id"`
	RFQID        int64     `db:"rfq_id"`
	Name         string    `db:"name"`
	TechCode     string    `db:"tech_code"`
	GOST         string    `db:"gost"`
	Unit         string    `db:"unit"`
	Qty          float64   `db:"qty"`
	Deadline     time.Time `db:"deadline"`
	Location     string    `db:"location"`
	PaymentTerms string    `db:"payment_terms"`
	TTOlRef      *string   `db:"tt_ol_ref"`
	RKDRef       *string   `db:"rkd_ref"`
}

// RFQRequest represents RFQ context
type RFQRequest struct {
	ID          int64    `db:"id"`
	City        string   `db:"city"`
	TotalBudget *float64 `db:"total_budget"`
}

// SupplierEmail represents supplier contact
type SupplierEmail struct {
	SupplierID int64  `db:"supplier_id"`
	Email      string `db:"email"`
	IsValid    bool   `db:"is_valid"`
}

// SupplierFoundEvent from Redis Stream
type SupplierFoundEvent struct {
	ItemID      string
	ItemName    string
	EmailsCount string
	Suppliers   []SupplierInfo
	StreamMsgID string
}

// SupplierInfo represents supplier data
type SupplierInfo struct {
	SupplierID int64    `json:"supplier_id"`
	Domain     string   `json:"domain"`
	Emails     []string `json:"emails"`
}

// RFQSend represents sent email record
type RFQSend struct {
	ID            int64     `db:"id"`
	ItemID        int64     `db:"item_id"`
	SupplierID    int64     `db:"supplier_id"`
	SMTPMessageID string    `db:"smtp_message_id"`
	SentAt        time.Time `db:"sent_at"`
}

// ParsedQuote represents extracted quote from email
type ParsedQuote struct {
	Price         float64
	DeliveryDays  int
	PickupAddress *string
	Confidence    float64
}

// SupplierThread represents email thread
type SupplierThread struct {
	ID          int64     `db:"id"`
	RFQSendID   int64     `db:"rfq_send_id"`
	Direction   string    `db:"direction"` // inbound/outbound
	Body        string    `db:"body"`
	NeedsReview bool      `db:"needs_review"`
	CreatedAt   time.Time `db:"created_at"`
}

// UserProfile represents company details of the RFQ creator
type UserProfile struct {
	CompanyName   string `db:"company_name"`
	Inn           string `db:"inn"`
	Kpp           string `db:"kpp"`
	Address       string `db:"address"`
	Phone         string `db:"phone"`
	Email         string `db:"email"`
	ContactPerson string `db:"contact_person"`
}

// QuoteReceivedEvent for Redis Stream
type QuoteReceivedEvent struct {
	ItemID        string
	SupplierID    string
	SupplierEmail string
	Price         string
	DeliveryDays  string
	PickupAddress string
	Source        string
}

// QueuedEmail represents an email waiting for AI batch analysis
type QueuedEmail struct {
	ID            int64      `db:"id"`
	MessageID     string     `db:"message_id"`
	SupplierEmail string     `db:"supplier_email"`
	RFQID         *int64     `db:"rfq_id"`
	ItemID        *int64     `db:"item_id"`
	Subject       string     `db:"subject"`
	Body          string     `db:"body"`
	FromEmail     string     `db:"from_email"`
	RFQSendID     *int64     `db:"rfq_send_id"`
	Status        string     `db:"status"`
	BatchGroup    string     `db:"batch_group"`
	AIResult      *string    `db:"ai_result"`
	ErrorMessage  *string    `db:"error_message"`
	CreatedAt     time.Time  `db:"created_at"`
	ProcessedAt   *time.Time `db:"processed_at"`
}

// OrphanEmail represents an email that couldn't be matched to an RFQ
type OrphanEmail struct {
	ID           int64     `db:"id"`
	MessageID    string    `db:"message_id"`
	FromEmail    string    `db:"from_email"`
	Subject      string    `db:"subject"`
	Body         string    `db:"body"`
	Attachments  []string  `db:"attachments"`
	RawHeaders   string    `db:"raw_headers"`
	RetryCount   int       `db:"retry_count"`
	LastError    string    `db:"last_error"`
	Status       string    `db:"status"`
	CreatedAt    time.Time `db:"created_at"`
	UpdatedAt    time.Time `db:"updated_at"`
}

// QuoteHistory represents past quotes from a supplier
type QuoteHistory struct {
	ItemName      string    `db:"item_name"`
	Price         float64   `db:"price"`
	DeliveryDays  int       `db:"delivery_days"`
	PickupAddress string    `db:"pickup_address"`
	ReceivedAt    time.Time `db:"received_at"`
}

// ThreadMessage represents a message in supplier thread for context
type ThreadMessage struct {
	Direction string    `db:"direction"`
	Body      string    `db:"body"`
	CreatedAt time.Time `db:"created_at"`
}
