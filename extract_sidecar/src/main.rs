mod ocr;

use anyhow::{Context, Result};
use axum::{
    extract::{Multipart, State},
    http::{HeaderValue, StatusCode},
    routing::post,
    Json, Router,
};
use chrono::{DateTime, Duration, Utc};
use hex::encode as hex_encode;
use serde::Serialize;
use sha2::{Digest, Sha256};
use sqlx::{postgres::PgPoolOptions, FromRow, PgPool};
use std::path::Path;
use tower_http::cors::{AllowHeaders, AllowMethods, AllowOrigin, CorsLayer};
use uuid::Uuid;

// ── App state ─────────────────────────────────────────────────────────────────

#[derive(Clone)]
struct AppState {
    db: PgPool,
    api_key: String,
}

// ── Auth middleware ───────────────────────────────────────────────────────────

async fn require_api_key(
    State(state): State<AppState>,
    request: axum::extract::Request,
    next: axum::middleware::Next,
) -> Result<axum::response::Response, StatusCode> {
    let token = request
        .headers()
        .get("Authorization")
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.strip_prefix("Bearer "));
    match token {
        Some(t) if t == state.api_key => Ok(next.run(request).await),
        _ => Err(StatusCode::UNAUTHORIZED),
    }
}

// ── Response / DB types ───────────────────────────────────────────────────────

#[derive(Serialize)]
struct ExtractTextResponse {
    /// Stable document ID — pass to FastAPI to reference the source doc.
    doc_id: String,
    filename: String,
    /// Full extracted text, all pages joined with \n\n.
    text: String,
    /// true = served from DB cache; false = freshly OCR'd.
    cache_hit: bool,
    /// "tesseract" | "openai_vision" | "none" (plain-text files)
    ocr_provider: String,
}

#[derive(FromRow)]
struct CachedDoc {
    id: String,
    extracted_text: String,
    ocr_provider: String,
    filename: String,
}

fn err(status: StatusCode, msg: impl Into<String>) -> (StatusCode, Json<serde_json::Value>) {
    (status, Json(serde_json::json!({ "error": msg.into() })))
}

// ── Format classifier ─────────────────────────────────────────────────────────

fn classify_format(filename: &str) -> &'static str {
    match Path::new(filename)
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_lowercase()
        .as_str()
    {
        "pdf" | "jpg" | "jpeg" | "png" => "ocr",
        "txt" | "md" => "text",
        _ => "unsupported",
    }
}

fn content_hash(bytes: &[u8]) -> String {
    hex_encode(Sha256::digest(bytes))
}

fn expires_at_from_days(now: DateTime<Utc>, expires_in_days: Option<i64>) -> Option<DateTime<Utc>> {
    expires_in_days.map(|d| now + Duration::days(d))
}

impl From<CachedDoc> for ExtractTextResponse {
    fn from(doc: CachedDoc) -> Self {
        Self {
            doc_id: doc.id,
            filename: doc.filename,
            text: doc.extracted_text,
            cache_hit: true,
            ocr_provider: doc.ocr_provider,
        }
    }
}

// ── Handler ───────────────────────────────────────────────────────────────────

/// POST /extract-text
///
/// Multipart fields:
///   file            — document to extract (pdf, jpg, jpeg, png, txt, md)
///   expires_in_days — optional TTL integer; omit for permanent storage
///   source_url      — optional canonical URL for audit/cache metadata
///
/// Flow:
///   1. SHA-256 hash the raw bytes.
///   2. Check extracted_documents for a non-expired hit → return immediately.
///   3. Miss: write tempfile → OCR → store result.
///   4. Return { doc_id, text, cache_hit, ocr_provider, filename }.
async fn extract_text_handler(
    State(state): State<AppState>,
    mut multipart: Multipart,
) -> Result<Json<ExtractTextResponse>, (StatusCode, Json<serde_json::Value>)> {
    let mut file_data: Option<(String, Vec<u8>)> = None;
    let mut expires_in_days: Option<i64> = None;
    let mut source_url: Option<String> = None;

    while let Some(field) = multipart
        .next_field()
        .await
        .map_err(|e| err(StatusCode::BAD_REQUEST, e.to_string()))?
    {
        match field.name() {
            Some("expires_in_days") => {
                let s = field
                    .text()
                    .await
                    .map_err(|e| err(StatusCode::BAD_REQUEST, e.to_string()))?;
                expires_in_days = s.trim().parse::<i64>().ok();
            }
            Some("source_url") => {
                let s = field
                    .text()
                    .await
                    .map_err(|e| err(StatusCode::BAD_REQUEST, e.to_string()))?;
                let trimmed = s.trim();
                if !trimmed.is_empty() {
                    source_url = Some(trimmed.to_string());
                }
            }
            _ => {
                let filename = field.file_name().unwrap_or("upload").to_string();
                let bytes = field
                    .bytes()
                    .await
                    .map_err(|e| err(StatusCode::BAD_REQUEST, e.to_string()))?
                    .to_vec();
                file_data = Some((filename, bytes));
            }
        }
    }

    let (filename, bytes) =
        file_data.ok_or_else(|| err(StatusCode::BAD_REQUEST, "No file uploaded"))?;

    let fmt = classify_format(&filename);
    if fmt == "unsupported" {
        let ext = Path::new(&filename)
            .extension()
            .and_then(|e| e.to_str())
            .unwrap_or("(none)");
        return Err(err(
            StatusCode::BAD_REQUEST,
            format!("Unsupported file type '.{ext}'. Accepted: pdf, jpg, jpeg, png, txt, md."),
        ));
    }

    // --- 1. Hash ---
    let hash = content_hash(&bytes);

    // --- 2. Cache check ---
    let cached = sqlx::query_as::<_, CachedDoc>(
        r#"
        SELECT id, extracted_text, ocr_provider, filename
        FROM   extracted_documents
        WHERE  content_hash = $1
          AND  (expires_at IS NULL OR expires_at > NOW())
        LIMIT  1
        "#,
    )
    .bind(&hash)
    .fetch_optional(&state.db)
    .await
    .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    if let Some(doc) = cached {
        return Ok(Json(doc.into()));
    }

    // --- 3. Extract ---
    let (text, ocr_provider) = if fmt == "ocr" {
        let suffix = Path::new(&filename)
            .extension()
            .and_then(|e| e.to_str())
            .map(|e| format!(".{e}"))
            .unwrap_or_default();

        // tempfile::NamedTempFile cleans up on drop — no manual unlink needed.
        let tmp = tempfile::Builder::new()
            .prefix("sidecar_")
            .suffix(&suffix)
            .tempfile()
            .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

        tokio::fs::write(tmp.path(), &bytes)
            .await
            .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

        let (t, p) = ocr::extract_text_with_provider(tmp.path())
            .await
            .map_err(|e| {
                err(
                    StatusCode::INTERNAL_SERVER_ERROR,
                    format!("OCR failed: {e:#}"),
                )
            })?;

        (t, p.to_string())
    } else {
        let t = String::from_utf8(bytes.clone())
            .unwrap_or_else(|_| String::from_utf8_lossy(&bytes).into_owned());
        (t, "none".to_string())
    };

    if text.trim().is_empty() {
        return Err(err(
            StatusCode::UNPROCESSABLE_ENTITY,
            "File produced no extractable text.",
        ));
    }

    // --- 4. Store ---
    let doc_id = Uuid::new_v4().to_string();
    let src_type = Path::new(&filename)
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("unknown")
        .to_string();
    let expires_at = expires_at_from_days(Utc::now(), expires_in_days);

    sqlx::query(
        r#"
        INSERT INTO extracted_documents
            (id, content_hash, source_url, filename, source_type, ocr_provider, extracted_text, expires_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (content_hash) DO NOTHING
        "#,
    )
    .bind(&doc_id).bind(&hash).bind(&source_url).bind(&filename)
    .bind(&src_type).bind(&ocr_provider).bind(&text).bind(expires_at)
    .execute(&state.db)
    .await
    .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    // Canonical id — may differ from doc_id if concurrent insert won the race.
    let actual_id = sqlx::query_scalar::<_, String>(
        "SELECT id FROM extracted_documents WHERE content_hash = $1",
    )
    .bind(&hash)
    .fetch_one(&state.db)
    .await
    .map_err(|e| err(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    Ok(Json(ExtractTextResponse {
        doc_id: actual_id,
        filename,
        text,
        cache_hit: false,
        ocr_provider,
    }))
}

// ── Bootstrap ─────────────────────────────────────────────────────────────────

fn build_app(state: AppState) -> Router {
    let cors = CorsLayer::new()
        .allow_origin(AllowOrigin::list(["http://localhost:8000"
            .parse::<HeaderValue>()
            .unwrap()]))
        .allow_methods(AllowMethods::any())
        .allow_headers(AllowHeaders::any());

    let protected = Router::new()
        .route("/extract-text", post(extract_text_handler))
        .layer(axum::extract::DefaultBodyLimit::max(50 * 1024 * 1024))
        .layer(axum::middleware::from_fn_with_state(
            state.clone(),
            require_api_key,
        ));

    Router::new()
        .route("/health", axum::routing::get(|| async { "OK" }))
        .merge(protected)
        .layer(cors)
        .with_state(state)
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "extract_sidecar=info".parse().unwrap()),
        )
        .init();

    dotenvy::dotenv().ok();

    let database_url = std::env::var("DATABASE_URL").context("DATABASE_URL must be set")?;
    let api_key = std::env::var("SIDECAR_API_KEY").context("SIDECAR_API_KEY must be set")?;
    let addr = std::env::var("SIDECAR_ADDR").unwrap_or_else(|_| "0.0.0.0:4000".to_string());

    let db = PgPoolOptions::new()
        .max_connections(10)
        .connect(&database_url)
        .await
        .context("Failed to connect to database")?;

    let state = AppState { db, api_key };
    let app = build_app(state);

    tracing::info!("extract-sidecar listening on http://{}", addr);
    let listener = tokio::net::TcpListener::bind(&addr).await?;
    axum::serve(listener, app).await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{
        body::{to_bytes, Body},
        http::{header, Method, Request},
    };
    use serde_json::Value;
    use tower::ServiceExt;

    const TEST_API_KEY: &str = "test-sidecar-key";

    fn lazy_test_state() -> AppState {
        let db = PgPoolOptions::new()
            .connect_lazy("postgres://unused:unused@127.0.0.1:1/unused")
            .expect("test database URL should be syntactically valid");
        AppState {
            db,
            api_key: TEST_API_KEY.to_string(),
        }
    }

    fn multipart_txt_body(filename: &str, text: &str) -> (String, String) {
        let boundary = "sidecar-test-boundary";
        let body = format!(
            "--{boundary}\r\n\
             Content-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n\
             Content-Type: text/plain\r\n\
             \r\n\
             {text}\r\n\
             --{boundary}--\r\n"
        );
        (format!("multipart/form-data; boundary={boundary}"), body)
    }

    fn multipart_no_file_body() -> (String, String) {
        let boundary = "sidecar-test-boundary";
        let body = format!(
            "--{boundary}\r\n\
             Content-Disposition: form-data; name=\"expires_in_days\"\r\n\
             \r\n\
             7\r\n\
             --{boundary}--\r\n"
        );
        (format!("multipart/form-data; boundary={boundary}"), body)
    }

    fn multipart_file_without_filename_body(text: &str) -> (String, String) {
        let boundary = "sidecar-test-boundary";
        let body = format!(
            "--{boundary}\r\n\
             Content-Disposition: form-data; name=\"file\"\r\n\
             Content-Type: application/octet-stream\r\n\
             \r\n\
             {text}\r\n\
             --{boundary}--\r\n"
        );
        (format!("multipart/form-data; boundary={boundary}"), body)
    }

    fn malformed_multipart_body() -> (String, String) {
        let boundary = "sidecar-test-boundary";
        let body = format!(
            "--{boundary}\r\n\
             this-is-not-a-valid-header\r\n\
             \r\n"
        );
        (format!("multipart/form-data; boundary={boundary}"), body)
    }

    async fn response_json(response: axum::response::Response) -> Value {
        let bytes = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("response body should be readable");
        serde_json::from_slice(&bytes).expect("response should be JSON")
    }

    async fn assert_json_error_contains(
        response: axum::response::Response,
        status: StatusCode,
        expected: &str,
    ) {
        let actual_status = response.status();
        let json = response_json(response).await;
        let error = json["error"]
            .as_str()
            .expect("error response should include an error string");

        assert_eq!(actual_status, status);
        assert!(
            error.contains(expected),
            "expected error containing {expected:?}, got {error:?}"
        );
    }

    #[test]
    fn classifies_supported_and_unsupported_formats() {
        assert_eq!(classify_format("trade.pdf"), "ocr");
        assert_eq!(classify_format("scan.JPG"), "ocr");
        assert_eq!(classify_format("photo.jpeg"), "ocr");
        assert_eq!(classify_format("page.PNG"), "ocr");
        assert_eq!(classify_format("notes.txt"), "text");
        assert_eq!(classify_format("README.MD"), "text");
        assert_eq!(classify_format("archive.zip"), "unsupported");
        assert_eq!(classify_format("no-extension"), "unsupported");
    }

    #[test]
    fn content_hash_is_stable_and_content_sensitive() {
        let first = content_hash(b"same legal text");
        let second = content_hash(b"same legal text");
        let different = content_hash(b"different legal text");

        assert_eq!(first, second);
        assert_ne!(first, different);
        assert_eq!(first.len(), 64);
    }

    #[test]
    fn expiry_is_optional_and_day_based() {
        let now = DateTime::parse_from_rfc3339("2026-06-30T12:00:00Z")
            .unwrap()
            .with_timezone(&Utc);

        assert_eq!(expires_at_from_days(now, None), None);
        assert_eq!(
            expires_at_from_days(now, Some(7)),
            Some(
                DateTime::parse_from_rfc3339("2026-07-07T12:00:00Z")
                    .unwrap()
                    .with_timezone(&Utc)
            )
        );
    }

    #[test]
    fn cached_doc_maps_to_cache_hit_response() {
        let response = ExtractTextResponse::from(CachedDoc {
            id: "doc-123".to_string(),
            extracted_text: "cached text".to_string(),
            ocr_provider: "none".to_string(),
            filename: "fixture.txt".to_string(),
        });

        assert_eq!(response.doc_id, "doc-123");
        assert_eq!(response.filename, "fixture.txt");
        assert_eq!(response.text, "cached text");
        assert!(response.cache_hit);
        assert_eq!(response.ocr_provider, "none");
    }

    #[tokio::test]
    async fn extract_text_requires_bearer_token() {
        let app = build_app(lazy_test_state());
        let (content_type, body) = multipart_txt_body("fixture.txt", "hello sidecar");

        let response = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/extract-text")
                    .header(header::CONTENT_TYPE, content_type)
                    .body(Body::from(body))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn extract_text_rejects_wrong_bearer_token() {
        let app = build_app(lazy_test_state());
        let (content_type, body) = multipart_txt_body("fixture.txt", "hello sidecar");

        let response = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/extract-text")
                    .header(header::CONTENT_TYPE, content_type)
                    .header(header::AUTHORIZATION, "Bearer wrong-token")
                    .body(Body::from(body))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn extract_text_rejects_non_bearer_authorization() {
        let app = build_app(lazy_test_state());
        let (content_type, body) = multipart_txt_body("fixture.txt", "hello sidecar");

        let response = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/extract-text")
                    .header(header::CONTENT_TYPE, content_type)
                    .header(header::AUTHORIZATION, TEST_API_KEY)
                    .body(Body::from(body))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn extract_text_accepts_correct_bearer_token_before_validation() {
        let app = build_app(lazy_test_state());
        let (content_type, body) = multipart_txt_body("unsupported.docx", "hello sidecar");

        let response = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/extract-text")
                    .header(header::CONTENT_TYPE, content_type)
                    .header(header::AUTHORIZATION, format!("Bearer {TEST_API_KEY}"))
                    .body(Body::from(body))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_json_error_contains(response, StatusCode::BAD_REQUEST, "Unsupported file type")
            .await;
    }

    #[tokio::test]
    async fn extract_text_rejects_missing_file_before_db_lookup() {
        let app = build_app(lazy_test_state());
        let (content_type, body) = multipart_no_file_body();

        let response = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/extract-text")
                    .header(header::CONTENT_TYPE, content_type)
                    .header(header::AUTHORIZATION, format!("Bearer {TEST_API_KEY}"))
                    .body(Body::from(body))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_json_error_contains(response, StatusCode::BAD_REQUEST, "No file uploaded").await;
    }

    #[tokio::test]
    async fn extract_text_rejects_file_without_filename_as_unsupported() {
        let app = build_app(lazy_test_state());
        let (content_type, body) = multipart_file_without_filename_body("hello sidecar");

        let response = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/extract-text")
                    .header(header::CONTENT_TYPE, content_type)
                    .header(header::AUTHORIZATION, format!("Bearer {TEST_API_KEY}"))
                    .body(Body::from(body))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_json_error_contains(
            response,
            StatusCode::BAD_REQUEST,
            "Unsupported file type '.(none)'",
        )
        .await;
    }

    #[tokio::test]
    async fn extract_text_rejects_malformed_multipart_before_db_lookup() {
        let app = build_app(lazy_test_state());
        let (content_type, body) = malformed_multipart_body();

        let response = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/extract-text")
                    .header(header::CONTENT_TYPE, content_type)
                    .header(header::AUTHORIZATION, format!("Bearer {TEST_API_KEY}"))
                    .body(Body::from(body))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let json = response_json(response).await;
        assert!(
            json["error"]
                .as_str()
                .is_some_and(|error| !error.is_empty()),
            "malformed multipart should return a non-empty error body"
        );
    }

    #[tokio::test]
    async fn txt_upload_smoke_returns_200_then_cache_hit_when_test_db_is_configured() {
        let database_url = match std::env::var("TEST_DATABASE_URL") {
            Ok(url) => url,
            Err(_) => {
                eprintln!("skipping Postgres smoke test; set TEST_DATABASE_URL to run it");
                return;
            }
        };

        let db = PgPoolOptions::new()
            .max_connections(2)
            .connect(&database_url)
            .await
            .expect("TEST_DATABASE_URL should point to a reachable Postgres database");

        // The consolidated init.sql is the only production schema source. This
        // integration smoke therefore requires a database created by
        // `make db-reset` and validates the columns the sidecar depends on.
        let required_cache_columns: i64 = sqlx::query_scalar(
            r#"
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = ANY(current_schemas(false))
              AND table_name = 'extracted_documents'
              AND column_name = ANY($1)
            "#,
        )
        .bind(vec![
            "id",
            "content_hash",
            "source_url",
            "filename",
            "source_type",
            "ocr_provider",
            "extracted_text",
            "expires_at",
            "created_at",
        ])
        .fetch_one(&db)
        .await
        .expect("sidecar schema should be queryable");
        assert_eq!(
            required_cache_columns, 9,
            "TEST_DATABASE_URL must point to a database initialized by `make db-reset`"
        );

        let required_link_columns: i64 = sqlx::query_scalar(
            r#"
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = ANY(current_schemas(false))
              AND (table_name, column_name) IN (
                    ('documents', 'sidecar_doc_id'),
                    ('document_chunks', 'extracted_doc_id')
              )
            "#,
        )
        .fetch_one(&db)
        .await
        .expect("sidecar link schema should be queryable");
        assert_eq!(required_link_columns, 2, "init.sql sidecar links are incomplete");

        let fixture_text = format!("sidecar smoke fixture {}", Uuid::new_v4());
        let fixture_hash = content_hash(fixture_text.as_bytes());
        sqlx::query("DELETE FROM extracted_documents WHERE content_hash = $1")
            .bind(&fixture_hash)
            .execute(&db)
            .await
            .expect("fixture cleanup before test should succeed");

        let state = AppState {
            db: db.clone(),
            api_key: TEST_API_KEY.to_string(),
        };

        let first = post_txt_fixture(build_app(state.clone()), &fixture_text).await;
        assert_eq!(first.status(), StatusCode::OK);
        let first_json = response_json(first).await;
        assert_eq!(first_json["filename"], "fixture.txt");
        assert_eq!(first_json["text"], fixture_text);
        assert_eq!(first_json["cache_hit"], false);
        assert_eq!(first_json["ocr_provider"], "none");
        let doc_id = first_json["doc_id"]
            .as_str()
            .expect("doc_id should be a string")
            .to_string();

        let second = post_txt_fixture(build_app(state), &fixture_text).await;
        assert_eq!(second.status(), StatusCode::OK);
        let second_json = response_json(second).await;
        assert_eq!(second_json["cache_hit"], true);
        assert_eq!(second_json["doc_id"], doc_id);

        sqlx::query("DELETE FROM extracted_documents WHERE content_hash = $1")
            .bind(&fixture_hash)
            .execute(&db)
            .await
            .expect("fixture cleanup after test should succeed");
    }

    async fn post_txt_fixture(app: Router, text: &str) -> axum::response::Response {
        let (content_type, body) = multipart_txt_body("fixture.txt", text);
        app.oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/extract-text")
                .header(header::CONTENT_TYPE, content_type)
                .header(header::AUTHORIZATION, format!("Bearer {TEST_API_KEY}"))
                .body(Body::from(body))
                .unwrap(),
        )
        .await
        .unwrap()
    }
}
