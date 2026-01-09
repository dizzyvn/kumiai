import { HTMLAttributes, forwardRef } from 'react';
import { getCardClass } from '../../styles/design-system';
import { components } from '../../styles/design-system';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  interactive?: boolean;
  padding?: keyof typeof components.card.padding;
}

export const Card = forwardRef<HTMLDivElement, CardProps>(
  ({ children, interactive = false, padding = 'md', className, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={`${getCardClass(interactive, padding)} ${className || ''}`}
        {...props}
      >
        {children}
      </div>
    );
  }
);

Card.displayName = 'Card';
