#ifndef PREFIXTREE_H
#define PREFIXTREE_H

#include <vector>
#include <map>
#include <memory>
#include <cassert>

template <typename ElemTy>
class PrefixTreeNode {
  ElemTy _value;
  std::vector<std::unique_ptr<PrefixTreeNode<ElemTy>>> _children;
public:

  PrefixTreeNode() = default;
  PrefixTreeNode(const ElemTy& val) : _value(val) {}
  PrefixTreeNode(ElemTy&& val) : _value(std::move(val)) {}

  template <typename IterableTy>
  PrefixTreeNode<ElemTy> *get(const IterableTy& seq) {
    auto *cur = this;
    for (auto& val : seq) {
      cur = cur->get(val);
      if (!cur)
        return nullptr;
    }

    return cur;
  }

  template <typename IterableTy>
  PrefixTreeNode<ElemTy> *get_longest_prefix(const IterableTy& seq) {
    auto *cur = this;
    auto *tmp = cur;
    for (auto& val : seq) {
      tmp = cur->get(val);
      if (!cur)
        return tmp;
      cur = tmp;
    }

    return cur;
  }

  PrefixTreeNode<ElemTy> *get(const ElemTy& val) {
    for (auto& chld : _children) {
      if (chld->value() == val)
        return chld.get();
    }

    return nullptr;
  }

  template <typename IterableTy>
  std::pair<PrefixTreeNode<ElemTy>*, bool>
  insert(const IterableTy& seq) {
    auto *node = this;
    bool isnew;
    for (auto& val : seq) {
      std::tie(node, isnew) = node->insert(val);
      assert(node);
    }
    return {node, isnew};
  }

  std::pair<PrefixTreeNode<ElemTy>*, bool>
  insert(const ElemTy& val) {
    auto *node = get(val);
    if (node)
      return {node, false};

    return {_children.emplace_back(new PrefixTreeNode<ElemTy>(val)).get(), true};
  }

  auto begin() -> auto { return _children.begin(); }
  auto end() -> auto { return _children.end(); }
  auto begin() const -> auto { return _children.begin(); }
  auto end() const -> auto { return _children.end(); }


  bool has_children() const { return !_children.empty(); }
  ElemTy& value() { return _value; }
  const ElemTy& value() const { return _value; }

};

template <typename ElemTy>
class PrefixTree {
  PrefixTreeNode<ElemTy> _root;

public:


  PrefixTreeNode<ElemTy> *get() { return &_root; }


  template <typename IterableTy>
  PrefixTreeNode<ElemTy> *get(const IterableTy& seq) {
    auto *cur = &_root;
    auto seq_it = seq.begin();
    auto seq_end = seq.end();
    assert(seq_it != seq_end && "Got empty sequence");

    while (cur) {
      cur = cur->get(*seq_it);
      if (++seq_it == seq_end)
        return cur;
    }

    return nullptr;
  }

  template <typename IterableTy>
  std::pair<PrefixTreeNode<ElemTy>*, bool>
  insert(const IterableTy& seq) {
    return _root.insert(seq);
  }

};

#endif
