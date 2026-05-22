#!/bin/bash

BACKEND_HOST="127.0.0.1"
BACKEND_PORT="${TRIM_SERVICE_PORT:-9855}"

if [ -f "${TRIM_PKGVAR}/config/config.yaml" ]; then
    PORT_FROM_CONFIG=$(grep -E "^[[:space:]]*port:" "${TRIM_PKGVAR}/config/config.yaml" 2>/dev/null | head -1 | sed 's/.*port:[[:space:]]*//' | tr -d '"' | tr -d "'")
    if [ -n "${PORT_FROM_CONFIG}" ]; then
        BACKEND_PORT="${PORT_FROM_CONFIG}"
    fi
fi

URI_NO_QUERY="${REQUEST_URI%%\?*}"
QUERY_STRING_PART=""
case "$REQUEST_URI" in
    *\?*) QUERY_STRING_PART="?${REQUEST_URI#*\?}" ;;
esac

REL_PATH="/"
case "$URI_NO_QUERY" in
    *index.cgi*)
        REL_PATH="${URI_NO_QUERY#*index.cgi}"
        ;;
esac

if [ -z "$REL_PATH" ]; then
    REL_PATH="/"
fi

TARGET_URL="http://${BACKEND_HOST}:${BACKEND_PORT}${REL_PATH}${QUERY_STRING_PART}"
METHOD="${REQUEST_METHOD:-GET}"

CURL_HEADERS=()
[ -n "${CONTENT_TYPE}" ] && CURL_HEADERS+=("-H" "Content-Type: ${CONTENT_TYPE}")
[ -n "${HTTP_AUTHORIZATION}" ] && CURL_HEADERS+=("-H" "Authorization: ${HTTP_AUTHORIZATION}")
[ -n "${HTTP_COOKIE}" ] && CURL_HEADERS+=("-H" "Cookie: ${HTTP_COOKIE}")
[ -n "${HTTP_X_REQUESTED_WITH}" ] && CURL_HEADERS+=("-H" "X-Requested-With: ${HTTP_X_REQUESTED_WITH}")

TMP_HEADERS=$(mktemp)
TMP_BODY=$(mktemp)
trap 'rm -f "${TMP_HEADERS}" "${TMP_BODY}"' EXIT

if [ "${METHOD}" = "POST" ] || [ "${METHOD}" = "PUT" ] || [ "${METHOD}" = "PATCH" ]; then
    cat - > "${TMP_BODY}"
    curl -sS -X "${METHOD}" --data-binary "@${TMP_BODY}" "${CURL_HEADERS[@]}" -D "${TMP_HEADERS}" "${TARGET_URL}" > "${TMP_BODY}.out" 2>/dev/null
else
    curl -sS -X "${METHOD}" "${CURL_HEADERS[@]}" -D "${TMP_HEADERS}" "${TARGET_URL}" > "${TMP_BODY}.out" 2>/dev/null
fi

CURL_EXIT=$?

if [ ${CURL_EXIT} -ne 0 ]; then
    echo "Status: 502 Bad Gateway"
    echo "Content-Type: text/plain; charset=utf-8"
    echo ""
    echo "Backend service unavailable (curl exit ${CURL_EXIT})"
    echo "Target: ${TARGET_URL}"
    exit 0
fi

STATUS_LINE=$(head -1 "${TMP_HEADERS}" | tr -d '\r')
STATUS_CODE=$(echo "${STATUS_LINE}" | awk '{print $2}')
STATUS_MSG=$(echo "${STATUS_LINE}" | cut -d' ' -f3-)

if [ -n "${STATUS_CODE}" ] && [ "${STATUS_CODE}" != "200" ]; then
    echo "Status: ${STATUS_CODE} ${STATUS_MSG}"
fi

grep -iE "^(Content-Type|Content-Length|Cache-Control|Location|Set-Cookie):" "${TMP_HEADERS}" | tr -d '\r'

echo ""
cat "${TMP_BODY}.out"
rm -f "${TMP_BODY}.out"
