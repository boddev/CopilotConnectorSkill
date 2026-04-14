// Throttle-resilient ingestion with batch concurrency control
// Shows: retry with exponential backoff on 429, semaphore-based concurrency
//   limiting, and auto-chunking based on payload size
//
// Prerequisites: npm install @microsoft/microsoft-graph-client @azure/identity

import { Client } from "@microsoft/microsoft-graph-client";

/** An external item to ingest into the Microsoft Graph index. */
interface ExternalItem {
  acl: Array<{ type: string; value: string; accessType: string }>;
  properties: Record<string, unknown>;
  content: {
    value: string;
    type: "text" | "html";
  };
}

/** Progress callback for batch ingestion. */
type ProgressCallback = (completed: number, total: number) => void;

/**
 * Provides throttle-resilient item ingestion with retry logic,
 * concurrency control, and automatic content chunking.
 */
class ResilientIngestion {
  constructor(
    private readonly graphClient: Client,
    private readonly connectionId: string
  ) {}

  /**
   * Ingest a single item with exponential backoff retry on throttling.
   *
   * @param itemId - Unique item identifier (must be URL-safe)
   * @param item - The external item payload
   * @param maxRetries - Maximum retry attempts (default: 5)
   */
  async ingestWithRetry(
    itemId: string,
    item: ExternalItem,
    maxRetries = 5
  ): Promise<void> {
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        await this.graphClient
          .api(`/external/connections/${this.connectionId}/items/${itemId}`)
          .put(item);
        return; // Success
      } catch (error: unknown) {
        const statusCode = (error as { statusCode?: number }).statusCode;
        if (statusCode !== 429 || attempt === maxRetries) {
          throw error;
        }

        // Prefer Retry-After header; fall back to exponential backoff
        const retryAfterHeader = (error as { headers?: Record<string, string> })
          .headers?.["retry-after"];
        const retryAfterSec = retryAfterHeader
          ? parseInt(retryAfterHeader, 10)
          : Math.pow(2, attempt);

        console.log(
          `Throttled on item ${itemId}. ` +
            `Retry ${attempt + 1}/${maxRetries} after ${retryAfterSec}s`
        );

        await new Promise((resolve) =>
          setTimeout(resolve, retryAfterSec * 1000)
        );
      }
    }
  }

  /**
   * Batch ingest items with controlled concurrency.
   * Uses a semaphore to limit parallel requests (recommended: 4–8,
   * never exceeding the 25 concurrent operations per connection limit).
   *
   * @param items - Map of item ID → external item payload
   * @param maxConcurrency - Maximum parallel requests (default: 4)
   * @param onProgress - Optional progress callback
   */
  async batchIngest(
    items: Map<string, ExternalItem>,
    maxConcurrency = 4,
    onProgress?: ProgressCallback
  ): Promise<void> {
    const semaphore = new Semaphore(maxConcurrency);
    let completed = 0;
    const total = items.size;

    const tasks = Array.from(items.entries()).map(
      async ([itemId, item]) => {
        await semaphore.acquire();
        try {
          await this.ingestWithRetry(itemId, item);
          completed++;
          onProgress?.(completed, total);
        } finally {
          semaphore.release();
        }
      }
    );

    await Promise.all(tasks);
  }

  /**
   * Check payload size before ingestion and auto-chunk if needed.
   * The 4 MB limit applies to the full serialized request body.
   *
   * @param itemId - Base item identifier
   * @param item - The external item payload (may be oversized)
   */
  async ingestWithAutoChunk(
    itemId: string,
    item: ExternalItem
  ): Promise<void> {
    const json = JSON.stringify(item);
    const byteSize = Buffer.byteLength(json, "utf-8");

    if (byteSize > 3_800_000) {
      // Leave 200 KB buffer below the 4 MB limit
      console.log(
        `Item ${itemId} is ${(byteSize / 1_000_000).toFixed(1)}MB — chunking required.`
      );

      const chunks = chunkContent(item.content.value, 3_500_000);

      for (let i = 0; i < chunks.length; i++) {
        const chunkedItem = cloneItemWithChunk(
          itemId,
          item,
          chunks[i],
          i,
          chunks.length
        );
        await this.ingestWithRetry(`${itemId}_chunk_${i}`, chunkedItem);
      }
    } else {
      await this.ingestWithRetry(itemId, item);
    }
  }
}

/**
 * Simple counting semaphore for concurrency control.
 * Limits the number of concurrent async operations.
 */
class Semaphore {
  private current = 0;
  private readonly waiting: Array<() => void> = [];

  constructor(private readonly max: number) {}

  /** Wait until a slot is available. */
  acquire(): Promise<void> {
    if (this.current < this.max) {
      this.current++;
      return Promise.resolve();
    }
    return new Promise<void>((resolve) => {
      this.waiting.push(resolve);
    });
  }

  /** Release a slot, waking the next waiter if any. */
  release(): void {
    const next = this.waiting.shift();
    if (next) {
      next();
    } else {
      this.current--;
    }
  }
}

/**
 * Split content at paragraph boundaries, respecting byte size limits.
 */
function chunkContent(content: string, maxChunkBytes: number): string[] {
  const paragraphs = content.split("\n\n").filter((p) => p.length > 0);
  const chunks: string[] = [];
  let current = "";
  let currentSize = 0;

  for (const para of paragraphs) {
    const paraSize = Buffer.byteLength(para, "utf-8");

    if (currentSize + paraSize > maxChunkBytes && current.length > 0) {
      chunks.push(current);
      current = "";
      currentSize = 0;
    }

    current += para + "\n\n";
    currentSize += paraSize;
  }

  if (current.length > 0) {
    chunks.push(current);
  }

  return chunks;
}

/**
 * Create a chunked version of an item with a unique ID and title context.
 */
function cloneItemWithChunk(
  originalId: string,
  original: ExternalItem,
  chunkContent: string,
  chunkIndex: number,
  totalChunks: number
): ExternalItem {
  const originalTitle =
    (original.properties.title as string) ?? "Document";

  const contextHeader =
    `Document: ${originalTitle}\n` +
    `Part ${chunkIndex + 1} of ${totalChunks}\n\n`;

  return {
    acl: original.acl,
    properties: {
      ...original.properties,
      title: `${originalTitle} (Part ${chunkIndex + 1} of ${totalChunks})`,
      parentDocumentId: originalId,
      chunkIndex,
      totalChunks,
    },
    content: {
      value: contextHeader + chunkContent,
      type: original.content.type,
    },
  };
}

export { ResilientIngestion, Semaphore, chunkContent, ExternalItem };
