import { useState, useCallback } from 'react';
import { AttachedFile } from '../components/FileAttachmentPreview';
import { config } from '@/lib/config';

const API_BASE = config.apiUrl;

interface PreparedFileInfo {
  id: string;
  name: string;
  size: number;
  type: string;
  expires_at: string;
}

interface FilePrepareResponse {
  prepared: PreparedFileInfo[];
  errors: Array<{ name: string; error: string }>;
}

interface CommittedFileInfo {
  name: string;
  path: string;
  size: number;
  type: string;
}

interface FileCommitResponse {
  committed: CommittedFileInfo[];
  errors: Array<{ name: string; error: string }>;
}

export const useFileUpload = (sessionId: string) => {
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([]);

  /**
   * Add files to the attachment list and upload them to temp storage
   */
  const addFiles = useCallback(async (files: File[]) => {
    // Add files to state immediately (show previews)
    const newAttachments: AttachedFile[] = files.map(file => ({
      id: '', // Will be set after upload
      file,
      name: file.name,
      size: file.size,
      type: file.type,
      progress: 0,
      status: 'uploading' as const,
    }));

    setAttachedFiles(prev => [...prev, ...newAttachments]);

    // Upload each file to temp storage
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const fileIndex = attachedFiles.length + i;

      try {
        const formData = new FormData();
        formData.append('files', file);

        // Upload to prepare endpoint
        const response = await fetch(
          `${API_BASE}/sessions/${sessionId}/files/prepare`,
          {
            method: 'POST',
            body: formData,
          }
        );

        if (!response.ok) {
          throw new Error(`Upload failed: ${response.statusText}`);
        }

        const result: FilePrepareResponse = await response.json();

        if (result.prepared.length > 0) {
          const prepared = result.prepared[0];

          // Update file with temp ID and mark as prepared
          setAttachedFiles(prev => {
            const updated = [...prev];
            const existingFileIndex = updated.findIndex(
              f => f.name === prepared.name && f.status === 'uploading' && !f.id
            );

            if (existingFileIndex >= 0) {
              updated[existingFileIndex] = {
                ...updated[existingFileIndex],
                id: prepared.id,
                progress: 100,
                status: 'prepared',
              };
            }

            return updated;
          });
        } else if (result.errors.length > 0) {
          // Mark as error
          setAttachedFiles(prev => {
            const updated = [...prev];
            const errorFileIndex = updated.findIndex(
              f => f.name === file.name && f.status === 'uploading'
            );

            if (errorFileIndex >= 0) {
              updated[errorFileIndex] = {
                ...updated[errorFileIndex],
                status: 'error',
                error: result.errors[0].error,
              };
            }

            return updated;
          });
        }
      } catch (error) {
        console.error('Failed to prepare file:', error);

        // Mark as error
        setAttachedFiles(prev => {
          const updated = [...prev];
          const errorFileIndex = updated.findIndex(
            f => f.name === file.name && f.status === 'uploading'
          );

          if (errorFileIndex >= 0) {
            updated[errorFileIndex] = {
              ...updated[errorFileIndex],
              status: 'error',
              error: String(error),
            };
          }

          return updated;
        });
      }
    }
  }, [sessionId, attachedFiles.length]);

  /**
   * Remove an attachment (and delete from temp storage if prepared)
   */
  const removeFile = useCallback(async (fileId: string) => {
    const file = attachedFiles.find(f => f.id === fileId || f.name === fileId);

    if (file?.id && file.status === 'prepared') {
      try {
        // Delete from temp storage
        await fetch(
          `${API_BASE}/sessions/${sessionId}/files/prepare?file_ids=${file.id}`,
          { method: 'DELETE' }
        );
      } catch (error) {
        console.error('Failed to delete temp file:', error);
      }
    }

    // Remove from state
    setAttachedFiles(prev => prev.filter(f => f.id !== fileId && f.name !== fileId));
  }, [sessionId, attachedFiles]);

  /**
   * Commit prepared files to session directory
   * Returns metadata string to append to message
   */
  const commitFiles = useCallback(async (targetDir: 'working' | 'result' = 'working'): Promise<string> => {
    const preparedFiles = attachedFiles.filter(f => f.status === 'prepared' && f.id);

    if (preparedFiles.length === 0) {
      return '';
    }

    try {
      const response = await fetch(
        `${API_BASE}/sessions/${sessionId}/files/commit`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            file_ids: preparedFiles.map(f => f.id),
            target_dir: targetDir,
          }),
        }
      );

      if (!response.ok) {
        throw new Error(`Commit failed: ${response.statusText}`);
      }

      const result: FileCommitResponse = await response.json();

      // Build file metadata string
      const fileMetadata = result.committed.map(file =>
        `- ${file.name} (${(file.size / 1024).toFixed(1)}KB) at ${file.path}`
      );

      // Clear attachments after successful commit
      setAttachedFiles([]);

      if (fileMetadata.length > 0) {
        return `\n\n📎 **Attached files:**\n${fileMetadata.join('\n')}`;
      }

      return '';
    } catch (error) {
      console.error('Failed to commit files:', error);
      throw error;
    }
  }, [sessionId, attachedFiles]);

  /**
   * Clear all attachments
   */
  const clearFiles = useCallback(() => {
    setAttachedFiles([]);
  }, []);

  return {
    attachedFiles,
    addFiles,
    removeFile,
    commitFiles,
    clearFiles,
    hasFiles: attachedFiles.length > 0,
    hasPreparedFiles: attachedFiles.some(f => f.status === 'prepared'),
  };
};
