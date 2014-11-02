typedef int (*NyHeapDef_SizeGetter) (PyObject *obj);
typedef struct {
    int flags;			/* As yet, only 0 */
    PyTypeObject *type;		/* The type it regards */
    NyHeapDef_SizeGetter size;
    void *traverse;
    void *relate;
    void *resv3, *resv4, *resv5; /* Reserved for future bin. comp. */
} NyHeapDef;

int gline_size(struct __pyx_obj_8printrun_11gcoder_line_GLine *gline) {
  int size = __pyx_type_8printrun_11gcoder_line_GLine.tp_basicsize;
  if (gline->_raw != NULL)
    size += strlen(gline->_raw) + 1;
  if (gline->_command != NULL)
    size += strlen(gline->_command) + 1;
  return size;
}

static NyHeapDef nysets_heapdefs[] = {
    {0, 0, (NyHeapDef_SizeGetter) gline_size},
};