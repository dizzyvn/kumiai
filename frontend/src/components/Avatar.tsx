import { useMemo } from 'react';
import { createAvatar } from '@dicebear/core';
import { notionists } from '@dicebear/collection';

interface AvatarProps {
  seed: string | null | undefined;
  size?: number;
  className?: string;
  color?: string;
}

export function Avatar({ seed, size = 48, className = '', color }: AvatarProps) {
  const avatarSvg = useMemo(() => {
    // Use a default seed if none provided
    const actualSeed = seed || 'default-avatar';
    const avatar = createAvatar(notionists, {
      seed: actualSeed,
      size,
    });
    return avatar.toString();
  }, [seed, size]);

  return (
    <div
      className={`mt-1 rounded-lg overflow-hidden flex items-center justify-center ${color ? '' : 'bg-primary-50'} ${className}`}
      style={color ? { backgroundColor: color } : undefined}
      dangerouslySetInnerHTML={{ __html: avatarSvg }}
    />
  );
}
