import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Props {
    content: string;
}

export default function MarkdownAnswer({ content }: Props) {
    return (
        <div className="markdown-answer">
            <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                    // Render images inline with artifact styling
                    img: ({ src, alt, ...rest }) => (
                        <img
                            src={src}
                            alt={alt || "Chart"}
                            className="inline-artifact-image"
                            loading="lazy"
                            {...rest}
                        />
                    ),
                    // Style tables
                    table: ({ children, ...rest }) => (
                        <div className="table-wrapper">
                            <table {...rest}>{children}</table>
                        </div>
                    ),
                    // Open links in new tab
                    a: ({ href, children, ...rest }) => (
                        <a href={href} target="_blank" rel="noopener noreferrer" {...rest}>
                            {children}
                        </a>
                    ),
                }}
            >
                {content}
            </ReactMarkdown>
        </div>
    );
}
