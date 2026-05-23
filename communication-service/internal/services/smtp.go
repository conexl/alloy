package services

import (
	"bytes"
	"context"
	"crypto/tls"
	"fmt"
	"mime"
	"mime/quotedprintable"
	"net"
	"net/smtp"
	"strings"
	"time"

	"communication-service/internal/config"

	"github.com/sirupsen/logrus"
	"golang.org/x/time/rate"
)

type SMTPClient struct {
	config  *config.Config
	logger  *logrus.Logger
	limiter *rate.Limiter
}

func NewSMTPClient(config *config.Config, logger *logrus.Logger) *SMTPClient {
	delay := config.SMTPDelay.Seconds()
	if delay <= 0 {
		delay = 1.0
	}
	return &SMTPClient{
		config:  config,
		logger:  logger,
		limiter: rate.NewLimiter(rate.Limit(1.0/delay), 1),
	}
}

type Email struct {
	To         []string
	CC         []string
	ReplyTo    string
	Subject    string
	HTMLBody   string
	TextBody   string
	InReplyTo  string
	References string
}

type SendResult struct {
	MessageID string
	Error     error
}

func (s *SMTPClient) Send(ctx context.Context, email *Email) (*SendResult, error) {
	if err := s.limiter.Wait(ctx); err != nil {
		return nil, fmt.Errorf("rate limiter error: %w", err)
	}

	messageID := s.generateMessageID()
	msg := s.buildEmail(email, messageID)

	to := email.To
	if len(to) == 0 {
		return nil, fmt.Errorf("no recipients specified")
	}

	smtpAddr := fmt.Sprintf("%s:%d", s.config.SMTPHost, s.config.SMTPPort)
	auth := smtp.PlainAuth("", s.config.SMTPUser, s.config.SMTPPass, s.config.SMTPHost)

	dialer := &net.Dialer{Timeout: 15 * time.Second}
	var conn net.Conn
	var client *smtp.Client
	var err error

	if s.config.SMTPPort == 465 {
		tlsConfig := &tls.Config{ServerName: s.config.SMTPHost}
		conn, err = tls.DialWithDialer(dialer, "tcp", smtpAddr, tlsConfig)
		if err != nil {
			return &SendResult{MessageID: messageID, Error: err}, err
		}
		client, err = smtp.NewClient(conn, s.config.SMTPHost)
		if err != nil {
			conn.Close()
			return &SendResult{MessageID: messageID, Error: err}, err
		}
		defer client.Close()

		if err = client.Auth(auth); err != nil {
			return &SendResult{MessageID: messageID, Error: err}, err
		}
	} else if s.config.SMTPPort == 1025 || s.config.SMTPPort == 25 {
		conn, err = dialer.DialContext(ctx, "tcp", smtpAddr)
		if err != nil {
			return &SendResult{MessageID: messageID, Error: err}, err
		}
		client, err = smtp.NewClient(conn, s.config.SMTPHost)
		if err != nil {
			conn.Close()
			return &SendResult{MessageID: messageID, Error: err}, err
		}
		defer client.Close()
	} else {
		conn, err = dialer.DialContext(ctx, "tcp", smtpAddr)
		if err != nil {
			return &SendResult{MessageID: messageID, Error: err}, err
		}
		client, err = smtp.NewClient(conn, s.config.SMTPHost)
		if err != nil {
			conn.Close()
			return &SendResult{MessageID: messageID, Error: err}, err
		}
		defer client.Close()

		if err = client.StartTLS(&tls.Config{ServerName: s.config.SMTPHost}); err != nil {
			return &SendResult{MessageID: messageID, Error: err}, err
		}
		if err = client.Auth(auth); err != nil {
			return &SendResult{MessageID: messageID, Error: err}, err
		}
	}

	if err = client.Mail(s.config.SMTPFrom); err != nil {
		return &SendResult{MessageID: messageID, Error: err}, err
	}
	for _, recipient := range to {
		if err = client.Rcpt(recipient); err != nil {
			return &SendResult{MessageID: messageID, Error: err}, err
		}
	}

	w, err := client.Data()
	if err != nil {
		return &SendResult{MessageID: messageID, Error: err}, err
	}
	if _, err = w.Write([]byte(msg)); err != nil {
		return &SendResult{MessageID: messageID, Error: err}, err
	}
	if err = w.Close(); err != nil {
		return &SendResult{MessageID: messageID, Error: err}, err
	}

	s.logger.WithFields(logrus.Fields{
		"message_id": messageID,
		"to":         strings.Join(to, ","),
		"subject":    email.Subject,
	}).Info("Email sent successfully")

	return &SendResult{MessageID: messageID, Error: nil}, nil
}

func (s *SMTPClient) generateMessageID() string {
	userPart := "comm"
	if idx := strings.Index(s.config.SMTPUser, "@"); idx > 0 {
		userPart = s.config.SMTPUser[:idx]
	}
	hostPart := strings.Split(s.config.SMTPHost, ".")[0]

	return fmt.Sprintf("<%d.%d.%s@%s>",
		time.Now().UnixNano(),
		time.Now().Unix(),
		userPart,
		hostPart,
	)
}

func encodeHeader(s string) string {
	for _, r := range s {
		if r > 127 {
			return mime.BEncoding.Encode("utf-8", s)
		}
	}
	return s
}

func (s *SMTPClient) buildEmail(email *Email, messageID string) string {
	var buf bytes.Buffer
	boundary := fmt.Sprintf("boundary_%d", time.Now().UnixNano())

	fromName := s.config.SMTPFrom
	if strings.Contains(fromName, "@") {
		buf.WriteString(fmt.Sprintf("From: %s\r\n", fromName))
	} else {
		buf.WriteString(fmt.Sprintf("From: %s <%s>\r\n", encodeHeader(fromName), s.config.SMTPFrom))
	}
	buf.WriteString(fmt.Sprintf("To: %s\r\n", strings.Join(email.To, ", ")))
	if len(email.CC) > 0 {
		buf.WriteString(fmt.Sprintf("CC: %s\r\n", strings.Join(email.CC, ", ")))
	}
	if email.ReplyTo != "" {
		buf.WriteString(fmt.Sprintf("Reply-To: %s\r\n", email.ReplyTo))
	}
	buf.WriteString(fmt.Sprintf("Subject: %s\r\n", encodeHeader(email.Subject)))
	buf.WriteString(fmt.Sprintf("Message-ID: %s\r\n", messageID))
	buf.WriteString(fmt.Sprintf("Date: %s\r\n", time.Now().Format(time.RFC1123Z)))
	buf.WriteString("MIME-Version: 1.0\r\n")
	buf.WriteString(fmt.Sprintf("Content-Type: multipart/alternative; boundary=\"%s\"\r\n", boundary))

	if email.InReplyTo != "" {
		buf.WriteString(fmt.Sprintf("In-Reply-To: %s\r\n", email.InReplyTo))
	}
	if email.References != "" {
		buf.WriteString(fmt.Sprintf("References: %s\r\n", email.References))
	}
	buf.WriteString("Auto-Submitted: auto-generated\r\n")
	buf.WriteString("\r\n")

	// Plain text part
	buf.WriteString(fmt.Sprintf("--%s\r\n", boundary))
	buf.WriteString("Content-Type: text/plain; charset=UTF-8\r\n")
	buf.WriteString("Content-Transfer-Encoding: quoted-printable\r\n\r\n")
	qpw := quotedprintable.NewWriter(&buf)
	qpw.Write([]byte(email.TextBody))
	qpw.Close()
	buf.WriteString("\r\n")

	// HTML part
	buf.WriteString(fmt.Sprintf("--%s\r\n", boundary))
	buf.WriteString("Content-Type: text/html; charset=UTF-8\r\n")
	buf.WriteString("Content-Transfer-Encoding: quoted-printable\r\n\r\n")
	qpw = quotedprintable.NewWriter(&buf)
	qpw.Write([]byte(email.HTMLBody))
	qpw.Close()
	buf.WriteString("\r\n")

	buf.WriteString(fmt.Sprintf("--%s--", boundary))

	return buf.String()
}
