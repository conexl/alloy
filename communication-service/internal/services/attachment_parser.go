package services

import (
	"archive/zip"
	"bytes"
	"io"
	"regexp"
	"strings"

	"github.com/ledongthuc/pdf"
	"github.com/sirupsen/logrus"
)

type AttachmentParser struct {
	logger *logrus.Logger
}

func NewAttachmentParser(logger *logrus.Logger) *AttachmentParser {
	return &AttachmentParser{logger: logger}
}

func (p *AttachmentParser) ExtractText(att *Attachment) string {
	switch {
	case strings.Contains(att.ContentType, "pdf"):
		return p.extractPDF(att.Content)
	case strings.Contains(att.ContentType, "wordprocessingml") ||
		strings.Contains(att.ContentType, "msword") ||
		strings.HasSuffix(strings.ToLower(att.Filename), ".docx"):
		return p.extractDOCX(att.Content)
	case strings.Contains(att.ContentType, "spreadsheetml") ||
		strings.Contains(att.ContentType, "excel") ||
		strings.HasSuffix(strings.ToLower(att.Filename), ".xlsx"):
		return p.extractXLSX(att.Content)
	case strings.HasPrefix(att.ContentType, "text/"):
		return string(att.Content)
	default:
		return ""
	}
}

func (p *AttachmentParser) extractPDF(data []byte) string {
	reader := bytes.NewReader(data)
	readAt := io.NewSectionReader(reader, 0, int64(len(data)))

	pdfReader, err := pdf.NewReader(readAt, int64(len(data)))
	if err != nil {
		p.logger.WithError(err).Debug("Failed to parse PDF")
		return ""
	}

	var textParts []string
	for i := 1; i <= pdfReader.NumPage(); i++ {
		page := pdfReader.Page(i)
		text, err := page.GetPlainText(nil)
		if err == nil && text != "" {
			textParts = append(textParts, text)
		}
	}

	return strings.Join(textParts, "\n")
}

func (p *AttachmentParser) extractDOCX(data []byte) string {
	r := bytes.NewReader(data)
	z, err := zip.NewReader(r, int64(len(data)))
	if err != nil {
		return ""
	}

	for _, f := range z.File {
		if f.Name == "word/document.xml" {
			rc, err := f.Open()
			if err != nil {
				return ""
			}
			defer rc.Close()

			content, err := io.ReadAll(rc)
			if err != nil {
				return ""
			}

			return stripXMLTags(string(content))
		}
	}
	return ""
}

func (p *AttachmentParser) extractXLSX(data []byte) string {
	r := bytes.NewReader(data)
	z, err := zip.NewReader(r, int64(len(data)))
	if err != nil {
		return ""
	}

	var texts []string
	for _, f := range z.File {
		if f.Name == "xl/sharedStrings.xml" {
			rc, err := f.Open()
			if err != nil {
				continue
			}
			defer rc.Close()

			content, err := io.ReadAll(rc)
			if err != nil {
				continue
			}

			texts = append(texts, stripXMLTags(string(content)))
		}
	}

	return strings.Join(texts, "\n")
}

var xmlTagRe = regexp.MustCompile(`<[^>]+>`)

func stripXMLTags(xml string) string {
	// Simple XML tag stripping
	text := xmlTagRe.ReplaceAllString(xml, " ")
	// Unescape common entities
	text = strings.ReplaceAll(text, "&lt;", "<")
	text = strings.ReplaceAll(text, "&gt;", ">")
	text = strings.ReplaceAll(text, "&amp;", "&")
	text = strings.ReplaceAll(text, "&quot;", "\"")
	text = strings.ReplaceAll(text, "&apos;", "'")
	// Normalize whitespace
	text = regexp.MustCompile(`\s+`).ReplaceAllString(text, " ")
	return strings.TrimSpace(text)
}
