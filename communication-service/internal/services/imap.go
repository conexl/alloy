package services

import (
	"bytes"
	"crypto/tls"
	"encoding/base64"
	"fmt"
	"io"
	"mime"
	"mime/multipart"
	"mime/quotedprintable"
	"net/mail"
	"net/textproto"
	"strings"
	"time"

	"github.com/emersion/go-imap"
	"github.com/emersion/go-imap/client"
	"github.com/sirupsen/logrus"
	"golang.org/x/text/encoding/charmap"
	"golang.org/x/text/encoding/simplifiedchinese"
	"golang.org/x/text/transform"
)

type IMAPClient struct {
	client *client.Client
	host   string
	port   int
	user   string
	pass   string
	folder string
	logger *logrus.Logger
}

func NewIMAPClient(host string, port int, user, pass, folder string, logger *logrus.Logger) *IMAPClient {
	return &IMAPClient{
		host:   host,
		port:   port,
		user:   user,
		pass:   pass,
		folder: folder,
		logger: logger,
	}
}

type headerGetter interface {
	Get(string) string
}

type Attachment struct {
	Filename    string
	ContentType string
	Size        int
	Content     []byte
}

type RawMessage struct {
	UID         uint32
	Date        time.Time
	From        string
	To          string
	Subject     string
	Body        string
	Attachments []Attachment
	InReplyTo   string
	MessageID   string
	References  string
}

func (c *IMAPClient) Connect() error {
	var err error

	addr := fmt.Sprintf("%s:%d", c.host, c.port)
	c.client, err = client.DialTLS(addr, &tls.Config{ServerName: c.host})
	if err != nil {
		fallbackPort := 143
		if c.port == 143 {
			fallbackPort = 993
		}
		addr = fmt.Sprintf("%s:%d", c.host, fallbackPort)
		c.client, err = client.Dial(addr)
		if err != nil {
			return fmt.Errorf("failed to connect to IMAP server: %w", err)
		}
		if err = c.client.StartTLS(&tls.Config{ServerName: c.host}); err != nil {
			c.client.Logout()
			return fmt.Errorf("failed to start TLS: %w", err)
		}
	}

	if err = c.client.Login(c.user, c.pass); err != nil {
		c.client.Logout()
		return fmt.Errorf("failed to login: %w", err)
	}

	if _, err = c.client.Select(c.folder, false); err != nil {
		c.client.Logout()
		return fmt.Errorf("failed to select folder: %w", err)
	}

	c.logger.Info("Connected to IMAP server")
	return nil
}

func (c *IMAPClient) Close() {
	if c.client != nil {
		c.client.Logout()
	}
}

func (c *IMAPClient) FetchUnseen() ([]RawMessage, error) {
	if c.client == nil {
		return nil, fmt.Errorf("not connected")
	}

	criteria := imap.NewSearchCriteria()
	criteria.WithoutFlags = []string{imap.SeenFlag}
	uids, err := c.client.Search(criteria)
	if err != nil {
		return nil, fmt.Errorf("failed to search messages: %w", err)
	}

	if len(uids) == 0 {
		return nil, nil
	}

	seqSet := new(imap.SeqSet)
	seqSet.AddNum(uids...)

	headerSection := &imap.BodySectionName{
		BodyPartName: imap.BodyPartName{Specifier: imap.HeaderSpecifier},
	}
	bodySection := &imap.BodySectionName{
		BodyPartName: imap.BodyPartName{Specifier: imap.EntireSpecifier},
	}

	messages := make(chan *imap.Message, 100)
	done := make(chan error, 1)

	go func() {
		done <- c.client.Fetch(seqSet, []imap.FetchItem{
			imap.FetchEnvelope,
			imap.FetchUid,
			imap.FetchFlags,
			headerSection.FetchItem(),
			bodySection.FetchItem(),
		}, messages)
	}()

	var results []RawMessage

	for msg := range messages {
		if msg.Envelope == nil {
			continue
		}

		inReplyTo := ""
		references := ""
		if lit, ok := msg.Body[headerSection]; ok {
			data, _ := io.ReadAll(lit)
			inReplyTo = extractHeader(string(data), "In-Reply-To")
			references = extractHeader(string(data), "References")
		}

		raw := RawMessage{
			UID:        msg.Uid,
			Date:       msg.Envelope.Date,
			Subject:    decodeRFC2047(msg.Envelope.Subject),
			InReplyTo:  inReplyTo,
			MessageID:  msg.Envelope.MessageId,
			References: references,
		}

		if len(msg.Envelope.From) > 0 {
			raw.From = formatAddress(msg.Envelope.From[0])
		}
		if len(msg.Envelope.To) > 0 {
			raw.To = formatAddress(msg.Envelope.To[0])
		}

		lit := msg.GetBody(bodySection)
		if lit != nil {
			rawBytes, err := io.ReadAll(lit)
			if err == nil {
				raw.Body, raw.Attachments = parseMessageBody(rawBytes)
			}
		}

		results = append(results, raw)
	}

	if err := <-done; err != nil {
		return nil, fmt.Errorf("failed to fetch messages: %w", err)
	}

	return results, nil
}

func (c *IMAPClient) FetchRecent(days int) ([]RawMessage, error) {
	if c.client == nil {
		return nil, fmt.Errorf("not connected")
	}

	since := time.Now().AddDate(0, 0, -days)
	criteria := imap.NewSearchCriteria()
	criteria.Since = since
	uids, err := c.client.UidSearch(criteria)
	if err != nil {
		return nil, fmt.Errorf("failed to search messages: %w", err)
	}

	if len(uids) == 0 {
		return nil, nil
	}

	// Limit to last 100 messages to avoid connection timeouts
	if len(uids) > 100 {
		uids = uids[len(uids)-100:]
	}

	c.logger.WithField("count", len(uids)).Info("Found recent messages")

	seqSet := new(imap.SeqSet)
	seqSet.AddNum(uids...)

	headerSection := &imap.BodySectionName{
		BodyPartName: imap.BodyPartName{Specifier: imap.HeaderSpecifier},
	}
	bodySection := &imap.BodySectionName{
		BodyPartName: imap.BodyPartName{Specifier: imap.EntireSpecifier},
	}

	messages := make(chan *imap.Message, 100)
	done := make(chan error, 1)

	go func() {
		done <- c.client.UidFetch(seqSet, []imap.FetchItem{
			imap.FetchEnvelope,
			imap.FetchUid,
			imap.FetchFlags,
			headerSection.FetchItem(),
			bodySection.FetchItem(),
		}, messages)
	}()

	var results []RawMessage

	for msg := range messages {
		if msg.Envelope == nil {
			continue
		}

		inReplyTo := ""
		references := ""
		if lit, ok := msg.Body[headerSection]; ok {
			data, _ := io.ReadAll(lit)
			inReplyTo = extractHeader(string(data), "In-Reply-To")
			references = extractHeader(string(data), "References")
		}

		raw := RawMessage{
			UID:        msg.Uid,
			Date:       msg.Envelope.Date,
			Subject:    decodeRFC2047(msg.Envelope.Subject),
			InReplyTo:  inReplyTo,
			MessageID:  msg.Envelope.MessageId,
			References: references,
		}

		if len(msg.Envelope.From) > 0 {
			raw.From = formatAddress(msg.Envelope.From[0])
		}
		if len(msg.Envelope.To) > 0 {
			raw.To = formatAddress(msg.Envelope.To[0])
		}

		lit := msg.GetBody(bodySection)
		if lit != nil {
			rawBytes, err := io.ReadAll(lit)
			if err == nil {
				raw.Body, raw.Attachments = parseMessageBody(rawBytes)
			}
		}

		results = append(results, raw)
	}

	if err := <-done; err != nil {
		return nil, fmt.Errorf("failed to fetch messages: %w", err)
	}

	c.logger.WithField("count", len(results)).Info("Fetched recent messages with bodies")
	return results, nil
}

func extractHeader(headers, name string) string {
	lines := strings.Split(headers, "\n")
	lowerName := strings.ToLower(name) + ":"
	for _, line := range lines {
		lowerLine := strings.ToLower(line)
		if strings.HasPrefix(lowerLine, lowerName) {
			return strings.TrimSpace(line[len(lowerName):])
		}
	}
	return ""
}

func (c *IMAPClient) MarkAsSeen(uid uint32) error {
	seqSet := new(imap.SeqSet)
	seqSet.AddNum(uid)

	item := imap.FormatFlagsOp(imap.AddFlags, true)
	flags := []interface{}{imap.SeenFlag}

	return c.client.Store(seqSet, item, flags, nil)
}

func formatAddress(addr *imap.Address) string {
	if addr == nil {
		return ""
	}
	personal := decodeRFC2047(addr.PersonalName)
	email := fmt.Sprintf("%s@%s", addr.MailboxName, addr.HostName)
	if personal != "" {
		return fmt.Sprintf("%s <%s>", personal, email)
	}
	return email
}

func decodeRFC2047(s string) string {
	if s == "" {
		return ""
	}
	d := mime.WordDecoder{
		CharsetReader: func(charset string, input io.Reader) (io.Reader, error) {
			switch strings.ToLower(charset) {
			case "koi8-r", "koi8r":
				return transform.NewReader(input, charmap.KOI8R.NewDecoder()), nil
			case "windows-1251", "cp1251", "cp-1251":
				return transform.NewReader(input, charmap.Windows1251.NewDecoder()), nil
			default:
				return nil, fmt.Errorf("unsupported charset: %s", charset)
			}
		},
	}
	decoded, err := d.DecodeHeader(s)
	if err != nil {
		return s
	}
	return decoded
}

func parseMessageBody(raw []byte) (string, []Attachment) {
	if len(raw) == 0 {
		return "", nil
	}

	msg, err := mail.ReadMessage(bytes.NewReader(raw))
	if err != nil {
		return decodeText(raw, "utf-8"), nil
	}

	mediaType, params, err := mime.ParseMediaType(msg.Header.Get("Content-Type"))
	if err != nil {
		mediaType = "text/plain"
	}

	var attachments []Attachment
	var body string
	if strings.HasPrefix(mediaType, "multipart/") {
		body = readMultipartBody(msg.Body, params["boundary"], &attachments)
	} else {
		body = readSinglePartBody(msg.Body, msg.Header)
	}

	return body, attachments
}

func readMultipartBody(body io.Reader, boundary string, attachments *[]Attachment) string {
	if boundary == "" {
		return ""
	}

	reader := multipart.NewReader(body, boundary)
	var textParts []string

	for {
		part, err := reader.NextPart()
		if err != nil {
			break
		}

		mediaType, params, _ := mime.ParseMediaType(part.Header.Get("Content-Type"))

		if strings.HasPrefix(mediaType, "multipart/") {
			_, innerParams, _ := mime.ParseMediaType(part.Header.Get("Content-Type"))
			if inner := readMultipartBody(part, innerParams["boundary"], attachments); inner != "" {
				textParts = append(textParts, inner)
			}
			continue
		}

		if mediaType == "text/plain" {
			bodyBytes, _ := io.ReadAll(part)
			decoded := decodeMIMEBody(bodyBytes, part.Header)
			textParts = append([]string{decoded}, textParts...)
		} else if mediaType == "text/html" && len(textParts) == 0 {
			bodyBytes, _ := io.ReadAll(part)
			decoded := decodeMIMEBody(bodyBytes, part.Header)
			textParts = append(textParts, decoded)
		} else if isAttachment(part.Header) {
			bodyBytes, _ := io.ReadAll(part)
			decoded := decodeMIMEBody(bodyBytes, part.Header)
			filename := params["name"]
			if filename == "" {
				filename = part.FileName()
			}
			*attachments = append(*attachments, Attachment{
				Filename:    filename,
				ContentType: mediaType,
				Size:        len(decoded),
				Content:     []byte(decoded),
			})
		}
	}

	if len(textParts) > 0 {
		return textParts[0]
	}
	return ""
}

func isAttachment(h textproto.MIMEHeader) bool {
	disp := h.Get("Content-Disposition")
	if strings.Contains(strings.ToLower(disp), "attachment") {
		return true
	}
	// Also treat non-text parts as attachments if they have a filename
	if h.Get("Content-Type") != "" {
		_, params, _ := mime.ParseMediaType(h.Get("Content-Type"))
		if params["name"] != "" {
			return true
		}
	}
	return false
}

func readSinglePartBody(body io.Reader, h headerGetter) string {
	bodyBytes, err := io.ReadAll(body)
	if err != nil {
		return ""
	}
	return decodeMIMEBody(bodyBytes, h)
}

func decodeMIMEBody(data []byte, h headerGetter) string {
	enc := strings.ToLower(h.Get("Content-Transfer-Encoding"))
	_, params, _ := mime.ParseMediaType(h.Get("Content-Type"))
	charset := params["charset"]

	var decoded []byte
	var err error

	switch {
	case enc == "base64":
		clean := strings.TrimSpace(string(data))
		decoded, err = base64.StdEncoding.DecodeString(clean)
		if err != nil {
			decoded = data
		}
	case enc == "quoted-printable":
		decoded, err = io.ReadAll(quotedprintable.NewReader(bytes.NewReader(data)))
		if err != nil {
			decoded = data
		}
	default:
		decoded = data
	}

	return decodeText(decoded, charset)
}

func decodeText(data []byte, charset string) string {
	charset = strings.ToLower(strings.TrimSpace(charset))
	charset = strings.TrimPrefix(charset, "\"")
	charset = strings.TrimSuffix(charset, "\"")

	switch charset {
	case "utf-8", "utf8", "":
		return string(data)
	case "windows-1251", "cp1251", "cp-1251":
		decoder := charmap.Windows1251.NewDecoder()
		decoded, err := decoder.Bytes(data)
		if err == nil {
			return string(decoded)
		}
	case "koi8-r", "koi8r":
		decoder := charmap.KOI8R.NewDecoder()
		decoded, err := decoder.Bytes(data)
		if err == nil {
			return string(decoded)
		}
	case "iso-8859-1", "latin1":
		decoder := charmap.ISO8859_1.NewDecoder()
		decoded, err := decoder.Bytes(data)
		if err == nil {
			return string(decoded)
		}
	case "gbk", "gb2312", "gb18030":
		decoder := simplifiedchinese.GBK.NewDecoder()
		decoded, _, err := transform.Bytes(decoder, data)
		if err == nil {
			return string(decoded)
		}
	default:
		decoder := charmap.Windows1251.NewDecoder()
		decoded, err := decoder.Bytes(data)
		if err == nil {
			return string(decoded)
		}
	}

	return string(data)
}
