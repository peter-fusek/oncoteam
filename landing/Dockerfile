FROM nginx:alpine
COPY index.html style.css i18n.js og-image.png favicon.ico apple-touch-icon.png /usr/share/nginx/html/
COPY robots.txt sitemap.xml llms.txt llms-full.txt /usr/share/nginx/html/
COPY sprava-lekarskych-dokumentov.html pred-navstevou-onkologa.html /usr/share/nginx/html/
COPY health /usr/share/nginx/html/health
EXPOSE 80
