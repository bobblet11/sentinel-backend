{
  article: {
    title: string;
    url: string;
    content: string;           // Preview (max ~1800 chars)
    source: string;            // News outlet name
    publishedAt: string;       // ISO 8601 date string
    author?: string;           // Optional
  };
  
  trustScore: number;          // 0-100 integer
  
  biasAnalysis: {
    overallBias: "left" | "center-left" | "center" | "center-right" | "right";
    biasScore: number;         // -100 to +100 integer
    confidence: number;        // 0-100 integer (percentage)
    sentiment: "positive" | "neutral" | "negative";
    indicators: {
      language: string;        // Textual description
      sources: string;         // Textual description
      framing: string;         // Textual description
    };
  };
  
  keyClaims: Array<{
    id: string;
    claim: string;
    verdict: "true" | "mostly-true" | "mixed" | "mostly-false" | "false" | "unverified";
    confidence: number;        // 0-100 integer (percentage)
    evidence: Array<{
      source: string;          // Source name/description
      url: string;             // Evidence URL
      excerpt: string;         // Relevant excerpt/quote
    }>;
  }>;
<!--   
  relatedArticles: Array<{
    id: string;
    title: string;
    source: string;            // News outlet name
    url: string;               // Article URL
    bias: "left" | "center-left" | "center" | "center-right" | "right";
    publishedAt: string;       // ISO 8601 date string
    excerpt: string;           // Article summary/preview
  }>; -->
}